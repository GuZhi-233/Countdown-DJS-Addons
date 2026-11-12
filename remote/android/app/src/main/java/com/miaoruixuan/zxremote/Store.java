package com.miaoruixuan.zxremote;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.UUID;

public final class Store {
    private final SharedPreferences prefs;

    public Store(Context context) {
        prefs = context.getSharedPreferences("zx_remote", Context.MODE_PRIVATE);
        if (!prefs.contains("device_id")) {
            prefs.edit().putString("device_id", UUID.randomUUID().toString().replace("-", "")).apply();
        }
        if (!prefs.contains("device_name")) {
            prefs.edit().putString("device_name", android.os.Build.MODEL).apply();
        }
    }

    public String deviceId() {
        return prefs.getString("device_id", "");
    }

    public String deviceName() {
        return prefs.getString("device_name", android.os.Build.MODEL);
    }

    public void setDeviceName(String name) {
        prefs.edit().putString("device_name", str(name, android.os.Build.MODEL)).apply();
    }

    public String theme() {
        return prefs.getString("theme", "system");
    }

    public void setTheme(String theme) {
        prefs.edit().putString("theme", str(theme, "system")).apply();
    }

    public String lastHost() {
        return prefs.getString("last_host", "");
    }

    public void setLastHost(String id) {
        prefs.edit().putString("last_host", str(id, "")).apply();
    }

    public JSONArray hosts() {
        try {
            return new JSONArray(prefs.getString("hosts", "[]"));
        } catch (Exception exc) {
            return new JSONArray();
        }
    }

    public JSONObject findHost(String id) {
        JSONArray rows = hosts();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.optJSONObject(index);
            if (row != null && str(row.optString("id"), "").equals(str(id, ""))) {
                return row;
            }
        }
        return null;
    }

    public void saveHost(JSONObject entry) {
        if (entry == null) {
            return;
        }
        String id = str(entry.optString("id"), "");
        if (id.isEmpty()) {
            return;
        }
        JSONArray rows = hosts();
        JSONArray result = new JSONArray();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.optJSONObject(index);
            if (row == null || str(row.optString("id"), "").equals(id)) {
                continue;
            }
            add(result, row);
        }
        add(result, entry);
        prefs.edit().putString("hosts", result.toString()).putString("last_host", id).apply();
    }

    public void removeHost(String id) {
        JSONArray rows = hosts();
        JSONArray result = new JSONArray();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.optJSONObject(index);
            if (row == null || str(row.optString("id"), "").equals(str(id, ""))) {
                continue;
            }
            add(result, row);
        }
        SharedPreferences.Editor editor = prefs.edit().putString("hosts", result.toString());
        if (str(lastHost(), "").equals(str(id, ""))) {
            editor.putString("last_host", "");
        }
        editor.apply();
    }

    public JSONArray history() {
        try {
            return new JSONArray(prefs.getString("history", "[]"));
        } catch (Exception exc) {
            return new JSONArray();
        }
    }

    public void addHistory(JSONObject entry) {
        JSONArray rows = history();
        JSONArray result = new JSONArray();
        if (entry != null) {
            add(result, entry);
        }
        for (int index = 0; index < rows.length() && result.length() < 20; index++) {
            JSONObject row = rows.optJSONObject(index);
            if (row != null) {
                add(result, row);
            }
        }
        prefs.edit().putString("history", result.toString()).apply();
    }

    private static void add(JSONArray array, Object value) {
        try {
            array.put(value);
        } catch (Exception ignored) {
        }
    }

    private static String str(String value, String fallback) {
        return value == null || value.isEmpty() ? fallback : value;
    }
}
