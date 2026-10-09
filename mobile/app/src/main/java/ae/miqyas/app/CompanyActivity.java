package ae.miqyas.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.net.HttpURLConnection;
import java.net.URL;

/** The first screen: which company. Opens straight into the last one used,
 *  so an engineer sees this once; "switch company" from the icon's long
 *  press brings it back. */
public class CompanyActivity extends Activity {
    static final String EXTRA_SWITCH = "switch";

    private EditText input;
    private Button go;
    private TextView error;
    private LinearLayout saved;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        String current = Companies.current(this);
        if (current != null && !wantsSwitch()) {
            open(current);
            return;
        }
        setContentView(R.layout.activity_company);
        input = findViewById(R.id.company);
        go = findViewById(R.id.go);
        error = findViewById(R.id.error);
        saved = findViewById(R.id.saved);
        ((TextView) findViewById(R.id.hint)).setText(
                getString(R.string.company_hint, getString(R.string.company_domain)));
        go.setOnClickListener(v -> check());
        input.setOnEditorActionListener((TextView v, int id, KeyEvent e) -> {
            if (id == EditorInfo.IME_ACTION_GO) { check(); return true; }
            return false;
        });
        showSaved();
    }

    /** The icon shortcut passes the flag as text, code passes it as a boolean. */
    private boolean wantsSwitch() {
        Intent i = getIntent();
        return i.getBooleanExtra(EXTRA_SWITCH, false) || "true".equals(i.getStringExtra(EXTRA_SWITCH));
    }

    private void showSaved() {
        saved.removeAllViews();
        for (String host : Companies.all(this)) {
            Button b = (Button) getLayoutInflater().inflate(R.layout.item_company, saved, false);
            b.setText(host);
            b.setOnClickListener(v -> open(host));
            b.setOnLongClickListener(v -> {
                new AlertDialog.Builder(this)
                        .setMessage(getString(R.string.forget_question, host))
                        .setPositiveButton(R.string.forget, (d, w) -> { Companies.forget(this, host); showSaved(); })
                        .setNegativeButton(R.string.cancel, null)
                        .show();
                return true;
            });
            saved.addView(b);
        }
        findViewById(R.id.saved_title).setVisibility(saved.getChildCount() > 0 ? View.VISIBLE : View.GONE);
    }

    /** Asks the server before saving it, so a typo says so here rather than
     *  as a blank page inside the app. */
    private void check() {
        String host = Companies.hostFor(input.getText().toString(), getString(R.string.company_domain));
        if (host == null) { error.setText(R.string.error_format); return; }
        error.setText("");
        go.setEnabled(false);
        go.setText(R.string.checking);
        Handler main = new Handler(Looper.getMainLooper());
        new Thread(() -> {
            boolean ok = reachable(host);
            main.post(() -> {
                go.setEnabled(true);
                go.setText(R.string.go);
                if (ok) open(host);
                else error.setText(getString(R.string.error_unreachable, host));
            });
        }).start();
    }

    private static boolean reachable(String host) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL("https://" + host + "/web/login").openConnection();
            c.setConnectTimeout(10000);
            c.setReadTimeout(10000);
            c.setInstanceFollowRedirects(true);
            int code = c.getResponseCode();
            c.disconnect();
            return code == 200;
        } catch (Exception e) {
            return false;
        }
    }

    private void open(String host) {
        Companies.use(this, host);
        Intent i = new Intent(this, MiqyasLauncher.class);
        i.setData(Uri.parse("https://" + host + "/odoo"));
        startActivity(i);
        finish();
    }
}
