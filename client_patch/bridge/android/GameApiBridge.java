package com.bandainamcoent.saomdeu;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.UUID;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * Source patch component for the SAO-CB request-ID bridge.
 *
 * The native request hook supplies the dispatcher fields and the original
 * Cocos pointers. This class assigns request_id, unwraps the dispatcher
 * envelope, and returns only its data/error object to native.
 */
public final class GameApiBridge {
    private static final String DISPATCH_ENDPOINT =
            "https://pibotv2-wflw.onrender.com/api/v4/dispatch";
    private static final String ORIGINAL_GAME_API_HOST =
            "api-defrag-eu.wrightflyer.net";
    private static final int CONNECT_TIMEOUT_MS = 12000;
    private static final int READ_TIMEOUT_MS = 30000;
    private static final int MAX_RESPONSE_BYTES = 8 * 1024 * 1024;
    private static final long REQUEST_DEADLINE_MS = 32000;
    private static final ExecutorService WORKERS = Executors.newFixedThreadPool(2);
    private static final ScheduledExecutorService DEADLINES =
            Executors.newSingleThreadScheduledExecutor();
    private static final ConcurrentHashMap<String, Pending> PENDING =
            new ConcurrentHashMap<String, Pending>();

    static {
        System.loadLibrary("saocb_bridge");
    }

    private GameApiBridge() {
    }

    /** Bridges requests to the pinned game's original GameAPI host. */
    public static String dispatchGameApiRequest(
            final String originalRequestUrl,
            final String originalRequestMethod,
            final byte[] originalRequestBody,
            final long httpClientPointer,
            final long httpRequestPointer) throws JSONException {
        if (originalRequestUrl == null || originalRequestMethod == null) {
            throw new JSONException("The original GameAPI URL and method are required.");
        }
        final URI originalUri;
        try {
            originalUri = new URL(originalRequestUrl).toURI();
        } catch (java.net.MalformedURLException | URISyntaxException error) {
            throw new JSONException("The original GameAPI URL is invalid.");
        }
        String originalHost = originalUri.getHost();
        if (originalHost != null && originalHost.endsWith(".")) {
            originalHost = originalHost.substring(0, originalHost.length() - 1);
        }
        if (!"https".equalsIgnoreCase(originalUri.getScheme())
                || originalUri.getRawUserInfo() != null
                || !ORIGINAL_GAME_API_HOST.equalsIgnoreCase(originalHost)) {
            throw new JSONException("The request is not addressed to the pinned GameAPI host.");
        }

        String path = originalUri.getPath();
        if (path == null || !path.startsWith("/api/")) {
            throw new JSONException("The original GameAPI path is outside the /api route.");
        }
        String route = path.substring("/api/".length());
        if (!isValidRoute(route)) {
            throw new JSONException("The original GameAPI path is invalid.");
        }

        final String method = originalRequestMethod.toUpperCase(java.util.Locale.ROOT);
        if (!("GET".equals(method)
                || "POST".equals(method)
                || "PUT".equals(method)
                || "PATCH".equals(method)
                || "DELETE".equals(method))) {
            throw new JSONException("The original GameAPI method is unsupported.");
        }

        final String bodyText = originalRequestBody == null
                ? ""
                : new String(originalRequestBody, StandardCharsets.UTF_8);
        final JSONObject payload;
        try {
            payload = bodyText.trim().isEmpty() ? new JSONObject() : new JSONObject(bodyText);
        } catch (JSONException error) {
            throw new JSONException("The original GameAPI body is not a JSON object.");
        }

        String gameUser = null;
        if (route.startsWith("user/") && !"user/register".equals(route)) {
            gameUser = route.substring("user/".length());
            if (!gameUser.matches("[A-Za-z0-9._~-]{1,128}")) {
                throw new JSONException("The original GameAPI user route has an invalid ID.");
            }
            if (payload.has("x_uid")
                    && !gameUser.equals(payload.optString("x_uid", null))) {
                throw new JSONException("The route ID does not match payload.x_uid.");
            }
        } else if (payload.has("x_uid")) {
            gameUser = payload.optString("x_uid", null);
            if (gameUser == null || !gameUser.matches("[A-Za-z0-9._~-]{1,128}")) {
                throw new JSONException("The original GameAPI body has an invalid x_uid.");
            }
        }

        JSONObject envelope = new JSONObject();
        envelope.put("protocol_version", 1);
        envelope.put("route", route);
        envelope.put("method", method);
        if (gameUser != null) {
            envelope.put("game_user", gameUser);
        }
        envelope.put("payload", payload);

        String routeForLog = route.startsWith("user/")
                && !"user/register".equals(route)
                ? "user/{uid}"
                : route;
        android.util.Log.i(
                "SAOCBBridge",
                "Intercepted legacy GameAPI " + method + " " + routeForLog);
        try {
            return dispatchNative(
                    new URL(DISPATCH_ENDPOINT),
                    envelope.toString(),
                    httpClientPointer,
                    httpRequestPointer);
        } catch (java.net.MalformedURLException error) {
            throw new JSONException("The SAO-CB dispatcher URL is invalid.");
        }
    }

    private static boolean isValidRoute(String route) {
        if (route == null
                || route.isEmpty()
                || !route.matches("[A-Za-z0-9._~/-]+")
                || route.startsWith("/")
                || route.endsWith("/")) {
            return false;
        }
        for (String segment : route.split("/")) {
            if (segment.isEmpty() || ".".equals(segment) || "..".equals(segment)) {
                return false;
            }
        }
        return true;
    }

    /**
     * Starts one bridged native request. Call on the Cocos thread while both
     * pointers refer to the live HttpClient and HttpRequest. The envelope must
     * contain the dispatcher fields but must not contain request_id.
     */
    public static String dispatchNative(
            final URL endpoint,
            final String envelopeWithoutRequestIdJson,
            final long httpClientPointer,
            final long httpRequestPointer) throws JSONException {
        if (endpoint == null || httpClientPointer == 0 || httpRequestPointer == 0) {
            throw new IllegalArgumentException(
                    "A valid endpoint and live Cocos request pointers are required.");
        }

        JSONObject envelope = new JSONObject(envelopeWithoutRequestIdJson);
        if (envelope.has("request_id")) {
            throw new IllegalArgumentException(
                    "The bridge generates request_id; omit it from the envelope.");
        }
        final String requestId = UUID.randomUUID().toString();
        envelope.put("request_id", requestId);

        if (!nativeRegisterResponse(
                requestId, httpClientPointer, httpRequestPointer)) {
            throw new IllegalStateException(
                    "The original Cocos response callback could not be registered.");
        }
        try {
            dispatch(endpoint, requestId, envelope.toString());
        } catch (JSONException error) {
            nativeOnResponse(
                    requestId,
                    499,
                    errorPayload(
                            "bridge_dispatch_error",
                            "The bridge could not start the native request."));
            return requestId;
        } catch (RuntimeException error) {
            nativeOnResponse(
                    requestId,
                    499,
                    errorPayload(
                            "bridge_dispatch_error",
                            "The bridge could not start the native request."));
            return requestId;
        }
        return requestId;
    }

    /**
     * Sends an already-formed dispatcher envelope and correlates the reply by
     * request_id. The native callback returns false for late or unregistered IDs.
     */
    public static void dispatch(
            final URL endpoint,
            final String requestId,
            final String envelopeJson) throws JSONException {
        if (endpoint == null || !isValidRequestId(requestId)) {
            throw new IllegalArgumentException("A valid endpoint and request_id are required.");
        }
        JSONObject envelope = new JSONObject(envelopeJson);
        if (!requestId.equals(envelope.optString("request_id", null))) {
            throw new IllegalArgumentException(
                    "The envelope request_id must match the pending native request.");
        }

        final byte[] requestBytes = envelopeJson.getBytes(java.nio.charset.Charset.forName("UTF-8"));
        final Pending pending = new Pending(requestId);
        if (PENDING.putIfAbsent(requestId, pending) != null) {
            throw new IllegalStateException("A request with this request_id is already pending.");
        }

        pending.deadline = DEADLINES.schedule(new Runnable() {
            @Override
            public void run() {
                complete(
                        pending,
                        504,
                        errorPayload("request_timeout", "The request deadline expired."));
                Future<?> worker = pending.worker;
                if (worker != null) {
                    worker.cancel(true);
                }
            }
        }, REQUEST_DEADLINE_MS, TimeUnit.MILLISECONDS);

        pending.worker = WORKERS.submit(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection connection = null;
                try {
                    connection = (HttpURLConnection) endpoint.openConnection();
                    connection.setRequestMethod("POST");
                    connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
                    connection.setReadTimeout(READ_TIMEOUT_MS);
                    connection.setUseCaches(false);
                    connection.setDoOutput(true);
                    connection.setFixedLengthStreamingMode(requestBytes.length);
                    connection.setRequestProperty(
                            "Content-Type", "application/json; charset=utf-8");
                    connection.setRequestProperty("Accept", "application/json");
                    connection.setRequestProperty("Accept-Encoding", "identity");
                    OutputStream output = connection.getOutputStream();
                    try {
                        output.write(requestBytes);
                    } finally {
                        output.close();
                    }

                    int status = connection.getResponseCode();
                    InputStream response = status >= 400
                            ? connection.getErrorStream()
                            : connection.getInputStream();
                    String responseJson = readUtf8(response);
                    JSONObject responseEnvelope = new JSONObject(responseJson);
                    if (!requestId.equals(responseEnvelope.optString("request_id", null))) {
                        complete(
                                pending,
                                502,
                                errorPayload(
                                        "request_id_mismatch",
                                        "The server response did not match the pending request."));
                        return;
                    }
                    JSONObject errorObject =
                            responseEnvelope.optJSONObject("error");
                    if (status < 200
                            || status >= 300
                            || !responseEnvelope.optBoolean("ok", false)) {
                        complete(
                                pending,
                                status >= 200 && status < 300 ? 502 : status,
                                errorObject != null
                                        ? errorObject.toString()
                                        : errorPayload(
                                                "invalid_dispatch_error",
                                                "The dispatcher returned an invalid error envelope."));
                        return;
                    }
                    JSONObject data = responseEnvelope.optJSONObject("data");
                    if (data == null) {
                        complete(
                                pending,
                                502,
                                errorPayload(
                                        "invalid_dispatch_data",
                                        "The dispatcher response did not contain a data object."));
                        return;
                    }
                    complete(pending, status, data.toString());
                } catch (Exception error) {
                    complete(
                            pending,
                            502,
                            errorPayload(
                                    "bridge_transport_error",
                                    "The request could not be completed by the bridge."));
                } finally {
                    if (connection != null) {
                        connection.disconnect();
                    }
                }
            }
        });
    }

    /** Cancels locally and reports the cancellation to the native registry once. */
    public static boolean cancel(String requestId) {
        Pending pending = PENDING.get(requestId);
        if (pending == null) {
            return false;
        }
        boolean delivered = complete(
                pending,
                499,
                errorPayload("request_cancelled", "The request was cancelled."));
        Future<?> worker = pending.worker;
        if (worker != null) {
            worker.cancel(true);
        }
        return delivered;
    }

    private static boolean complete(Pending pending, int status, String responseJson) {
        if (!pending.completed.compareAndSet(false, true)) {
            return false;
        }
        PENDING.remove(pending.requestId, pending);
        ScheduledFuture<?> deadline = pending.deadline;
        if (deadline != null) {
            deadline.cancel(false);
        }
        nativeOnResponse(pending.requestId, status, responseJson);
        return true;
    }

    private static native boolean nativeOnResponse(
            String requestId, int httpStatus, String responseBodyJson);

    private static native boolean nativeRegisterResponse(
            String requestId, long httpClientPointer, long httpRequestPointer);
    private static boolean isValidRequestId(String requestId) {
        if (requestId == null || requestId.length() < 1 || requestId.length() > 128) {
            return false;
        }
        for (int index = 0; index < requestId.length(); index++) {
            char value = requestId.charAt(index);
            if (!((value >= 'A' && value <= 'Z')
                    || (value >= 'a' && value <= 'z')
                    || (value >= '0' && value <= '9')
                    || value == '.' || value == '_' || value == ':' || value == '-')) {
                return false;
            }
        }
        return true;
    }

    private static String readUtf8(InputStream input) throws IOException {
        if (input == null) {
            throw new IOException("The HTTP response had no body.");
        }
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int total = 0;
        int count;
        while ((count = input.read(buffer)) != -1) {
            total += count;
            if (total > MAX_RESPONSE_BYTES) {
                throw new IOException("The HTTP response exceeded the bridge size limit.");
            }
            output.write(buffer, 0, count);
        }
        return new String(output.toByteArray(), java.nio.charset.Charset.forName("UTF-8"));
    }

    private static String errorPayload(String code, String message) {
        try {
            JSONObject error = new JSONObject();
            error.put("code", code);
            error.put("message", message);
            return error.toString();
        } catch (JSONException impossible) {
            throw new IllegalStateException("Could not encode a bridge error response.", impossible);
        }
    }

    private static final class Pending {
        final String requestId;
        final AtomicBoolean completed = new AtomicBoolean(false);
        volatile Future<?> worker;
        volatile ScheduledFuture<?> deadline;

        Pending(String requestId) {
            this.requestId = requestId;
        }
    }
}
