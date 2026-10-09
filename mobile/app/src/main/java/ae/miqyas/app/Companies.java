package ae.miqyas.app;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** The companies this phone has signed in to, newest first — like the
 *  accounts list in Odoo's app. Only addresses are kept; the password stays
 *  in Chrome's session for that address, never in the app. */
final class Companies {
    private static final String PREFS = "companies", LIST = "hosts", CURRENT = "current";

    private Companies() {}

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static List<String> all(Context c) {
        String raw = prefs(c).getString(LIST, "");
        List<String> out = new ArrayList<>();
        for (String h : raw.split("\n")) if (!h.isEmpty()) out.add(h);
        return out;
    }

    static String current(Context c) {
        return prefs(c).getString(CURRENT, null);
    }

    static void use(Context c, String host) {
        List<String> hosts = all(c);
        hosts.remove(host);
        hosts.add(0, host);
        prefs(c).edit().putString(LIST, String.join("\n", hosts)).putString(CURRENT, host).apply();
    }

    static void forget(Context c, String host) {
        List<String> hosts = all(c);
        hosts.remove(host);
        SharedPreferences.Editor e = prefs(c).edit().putString(LIST, String.join("\n", hosts));
        if (host.equals(current(c))) e.remove(CURRENT);
        e.apply();
    }

    /** "alamana" → alamana.miqyas.ae; anything with a dot is taken as the
     *  server's own address, the way Odoo's app accepts any server. */
    static String hostFor(String typed, String domain) {
        String t = typed.trim().toLowerCase();
        t = t.replaceFirst("^https?://", "");
        int slash = t.indexOf('/');
        if (slash >= 0) t = t.substring(0, slash);
        if (t.isEmpty()) return null;
        if (!t.contains(".")) {
            if (!t.matches("[a-z0-9][a-z0-9-]*")) return null;
            return t + "." + domain;
        }
        return t.matches("[a-z0-9.-]+(:[0-9]+)?") ? t : null;
    }
}
