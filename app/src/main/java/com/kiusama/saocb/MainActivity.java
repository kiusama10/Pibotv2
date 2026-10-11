package com.kiusama.saocb;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

public class MainActivity extends Activity {
    private WebView web;
    private ProgressBar progress;
    private LinearLayout errorView;
    private final String appUrl = BuildConfig.SAOCB_URL;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.rgb(6,17,31));
        getWindow().setNavigationBarColor(Color.rgb(6,17,31));
        buildUi();
        configureWebView();
        web.loadUrl(appUrl);
    }

    private void buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(6,17,31));

        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        FrameLayout.LayoutParams pp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, 6);
        pp.gravity = Gravity.TOP;
        root.addView(progress, pp);

        errorView = new LinearLayout(this);
        errorView.setOrientation(LinearLayout.VERTICAL);
        errorView.setGravity(Gravity.CENTER);
        errorView.setPadding(48, 48, 48, 48);
        errorView.setBackgroundColor(Color.rgb(6,17,31));
        errorView.setVisibility(View.GONE);

        TextView icon = new TextView(this);
        icon.setText("⚔");
        icon.setTextSize(56);
        icon.setTextColor(Color.rgb(111,231,255));
        icon.setGravity(Gravity.CENTER);
        errorView.addView(icon);

        TextView title = new TextView(this);
        title.setText("No pude entrar a Aincrad");
        title.setTextSize(23);
        title.setTextColor(Color.WHITE);
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, 24, 0, 12);
        errorView.addView(title);

        TextView help = new TextView(this);
        help.setText("Comprueba tu conexión y que PiBot esté Live en Render.");
        help.setTextSize(15);
        help.setTextColor(Color.rgb(147,172,192));
        help.setGravity(Gravity.CENTER);
        errorView.addView(help);

        Button retry = new Button(this);
        retry.setText("REINTENTAR");
        retry.setOnClickListener(v -> {
            errorView.setVisibility(View.GONE);
            web.setVisibility(View.VISIBLE);
            web.reload();
        });
        LinearLayout.LayoutParams rb = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        rb.setMargins(0, 30, 0, 0);
        errorView.addView(retry, rb);

        root.addView(errorView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(root);
    }

    private void configureWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setUserAgentString(s.getUserAgentString() + " SAOCB-Reborn-App/1.0");
        CookieManager.getInstance().setAcceptCookie(true);

        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int newProgress) {
                progress.setProgress(newProgress);
                progress.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }
        });

        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                Uri base = Uri.parse(appUrl);
                if (u.getHost() != null && u.getHost().equalsIgnoreCase(base.getHost())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) {}
                return true;
            }

            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    web.setVisibility(View.GONE);
                    errorView.setVisibility(View.VISIBLE);
                }
            }
        });
    }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (web != null) {
            web.stopLoading();
            web.destroy();
        }
        super.onDestroy();
    }
}
