package com.miaoruixuan.zxremote;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public final class DeviceManager implements DeviceSession.Callback {
    public interface Listener {
        void onSessionsChanged();

        void onSessionChanged(DeviceSession session);

        void onPaired(DeviceSession session);

        void onStateChanged(DeviceSession session);

        void onScheduleSaved(DeviceSession session, String rev);

        void onConflict(DeviceSession session, JSONObject state, String rev, String message);

        void onNotifyResult(DeviceSession session, boolean ok, String message);

        void onPairFailed(DeviceSession session, String message);

        void onRemoteChanged(DeviceSession session, String rev);
    }

    private final Store store;
    private final Listener listener;
    private final List<DeviceSession> sessions = new ArrayList<>();

    public DeviceManager(Store store, Listener listener) {
        this.store = store;
        this.listener = listener;
    }

    public void load() {
        sessions.clear();
        JSONArray rows = store.hosts();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.optJSONObject(index);
            if (row != null) {
                sessions.add(new DeviceSession(store, row, this));
            }
        }
        listener.onSessionsChanged();
    }

    public void connectAll() {
        for (DeviceSession session : new ArrayList<>(sessions)) {
            if (!session.token.isEmpty()) {
                session.connect();
            }
        }
    }

    public DeviceSession pairNew(String address, int port, String code) {
        JSONObject host = new JSONObject();
        put(host, "name", "新设备");
        put(host, "address", address);
        put(host, "port", port);
        DeviceSession session = new DeviceSession(store, host, this);
        session.pair(code, address, port);
        sessions.add(session);
        listener.onSessionsChanged();
        return session;
    }

    public List<DeviceSession> sessions() {
        return new ArrayList<>(sessions);
    }

    public DeviceSession find(String hostId) {
        for (DeviceSession session : sessions) {
            if (session.hostId.equals(hostId)) {
                return session;
            }
        }
        return null;
    }

    public void remove(DeviceSession session, boolean unpair) {
        if (session == null) {
            return;
        }
        if (unpair && session.isConnected()) {
            session.unpair();
        }
        session.closeClient();
        sessions.remove(session);
        if (!session.hostId.isEmpty()) {
            store.removeHost(session.hostId);
        }
        listener.onSessionsChanged();
    }

    public int removeInvalid() {
        int removed = 0;
        for (DeviceSession session : new ArrayList<>(sessions)) {
            if (session.status.contains("失效")) {
                session.closeClient();
                sessions.remove(session);
                if (!session.hostId.isEmpty()) {
                    store.removeHost(session.hostId);
                }
                removed += 1;
            }
        }
        if (removed > 0) {
            listener.onSessionsChanged();
        }
        return removed;
    }

    public JSONArray historyFor(String hostId) {
        JSONArray rows = store.history();
        JSONArray result = new JSONArray();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.optJSONObject(index);
            if (row == null) {
                continue;
            }
            if (hostId.equals(row.optString("hostId", ""))) {
                add(result, row);
            }
        }
        return result;
    }

    public void closeAll() {
        for (DeviceSession session : new ArrayList<>(sessions)) {
            session.closeClient();
        }
    }

    private void persist(DeviceSession session) {
        if (session.hostId.isEmpty() || session.token.isEmpty()) {
            return;
        }
        JSONObject entry = new JSONObject();
        put(entry, "id", session.hostId);
        put(entry, "name", session.hostName);
        put(entry, "address", session.address);
        put(entry, "port", session.port);
        put(entry, "token", session.token);
        put(entry, "alias", session.alias);
        put(entry, "version", session.hostVersion);
        put(entry, "last_seen", System.currentTimeMillis() / 1000);
        store.saveHost(entry);
    }

    @Override
    public void onSessionChanged(DeviceSession session) {
        persist(session);
        listener.onSessionChanged(session);
    }

    @Override
    public void onPaired(DeviceSession session) {
        persist(session);
        if (!sessions.contains(session)) {
            sessions.add(session);
        }
        listener.onPaired(session);
        listener.onSessionsChanged();
    }

    @Override
    public void onStateChanged(DeviceSession session) {
        listener.onStateChanged(session);
    }

    @Override
    public void onScheduleSaved(DeviceSession session, String rev) {
        persist(session);
        listener.onScheduleSaved(session, rev);
    }

    @Override
    public void onConflict(DeviceSession session, JSONObject state, String rev, String message) {
        listener.onConflict(session, state, rev, message);
    }

    @Override
    public void onNotifyResult(DeviceSession session, boolean ok, String message) {
        listener.onNotifyResult(session, ok, message);
    }

    @Override
    public void onPairFailed(DeviceSession session, String message) {
        if (session.hostId.isEmpty() && session.token.isEmpty()) {
            sessions.remove(session);
            listener.onSessionsChanged();
        }
        listener.onPairFailed(session, message);
    }

    @Override
    public void onRemoteChanged(DeviceSession session, String rev) {
        listener.onRemoteChanged(session, rev);
    }

    private static void put(JSONObject object, String key, Object value) {
        try {
            object.put(key, value);
        } catch (Exception ignored) {
        }
    }

    private static void add(JSONArray array, Object value) {
        try {
            array.put(value);
        } catch (Exception ignored) {
        }
    }
}
