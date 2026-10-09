package ae.miqyas.app;

import android.net.Uri;

import com.google.androidbrowserhelper.trusted.LauncherActivity;

/** Opens the chosen company full screen in Chrome's engine, which is what
 *  gives the app web notifications and the camera. */
public class MiqyasLauncher extends LauncherActivity {
    @Override
    protected Uri getLaunchingUrl() {
        Uri data = getIntent().getData();
        if (data != null) return data;
        String host = Companies.current(this);
        return host != null ? Uri.parse("https://" + host + "/odoo") : super.getLaunchingUrl();
    }
}
