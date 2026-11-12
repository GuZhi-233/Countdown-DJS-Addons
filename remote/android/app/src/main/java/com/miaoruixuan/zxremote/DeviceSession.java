package com.miaoruixuan.zxremote;

import org.json.JSONObject;

public final class DeviceSession implements Protocol.Client.Listener {
    public interface Callback {
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
    private final Callback callback;
    public String hostId = "";
    public String hostName = "ZX";
    public String hostVersion = "";
    public String address = "";
    public int port = Version.DEFAULT_CONTROL_PORT;
    public String token = "";
    public String alias = "";
    public JSONObject state = new JSONObject();
    public String rev = "";
    public boolean connected = false;
    public boolean connecting = false;
    public boolean pairing = false;
    public String status = "未连接";
    public String lastError = "";
    public Protocol.Client client;

    public DeviceSession(Store store, JSONObject host, Callback callback) {
        this.store = store;
        this.callback = callback;
        applyHost(host);
    }

    public void applyHost(JSONObject host) {
        if (host == null) {
            return;
        }
        hostId = host.optString("id", hostId);
        hostName = host.optString("name", hostName);
        hostVersion = host.optString("version", hostVersion);
        address = host.optString("address", address);
        port = host.optInt("port", port);
        token = host.optString("token", token);
        alias = host.optString("alias", alias);
    }

    public String displayName() {
        return alias == null || alias.trim().isEmpty() ? hostName : alias.trim();
    }

    public String key() {
        return hostId.isEmpty() ? address + ":" + port : hostId;
    }

    public void setAlias(String value) {
        alias = value == null ? "" : value.trim();
        callback.onSessionChanged(this);
    }

    public void connect() {
        if (token.isEmpty()) {
            status = "未配对";
            connected = false;
            callback.onSessionChanged(this);
            return;
        }
        closeClient();
        connecting = true;
        connected = false;
        status = "连接中…";
        lastError = "";
        callback.onSessionChanged(this);
        client = new Protocol.Client(this);
        client.hello(address, port, store.deviceId(), token, Version.VERSION);
    }

    public void pair(String code, String addressValue, int portValue) {
        address = addressValue;
        port = portValue;
        pairing = true;
        connecting = true;
        connected = false;
        status = "等待电脑端确认…";
        lastError = "";
        callback.onSessionChanged(this);
        closeClient();
        client = new Protocol.Client(this);
        client.pair(address, port, code, store.deviceId(), store.deviceName(), Version.VERSION);
    }

    public boolean isConnected() {
        return connected && client != null && client.isConnected();
    }

    public void requestSchedule() {
        if (client != null) {
            client.requestSchedule();
        }
    }

    public void saveSchedule(JSONObject value, String baseRev, boolean force) {
        if (client != null) {
            client.saveSchedule(value, baseRev, force);
        }
    }

    public void sendNotify(String title, String body, float duration) {
        if (client != null && isConnected()) {
            client.sendNotify("quick", title, body, duration);
        }
    }

    public void unpair() {
        if (client != null && isConnected()) {
            client.unpair();
        }
    }

    public void closeClient() {
        if (client != null) {
            client.close();
            client = null;
        }
    }

    @Override
    public void onPaired(JSONObject host, JSONObject newState, String newRev, String newToken) {
        if (host != null) {
            hostId = host.optString("id", hostId);
            hostName = host.optString("name", hostName);
            hostVersion = host.optString("version", hostVersion);
        }
        token = newToken == null ? "" : newToken;
        state = newState == null ? new JSONObject() : newState;
        rev = newRev == null ? "" : newRev;
        connected = true;
        connecting = false;
        pairing = false;
        status = "已连接";
        callback.onSessionChanged(this);
        callback.onPaired(this);
        callback.onStateChanged(this);
    }

    @Override
    public void onConnected(JSONObject host, JSONObject newState, String newRev) {
        if (host != null) {
            hostId = host.optString("id", hostId);
            hostName = host.optString("name", hostName);
            hostVersion = host.optString("version", hostVersion);
        }
        state = newState == null ? new JSONObject() : newState;
        rev = newRev == null ? "" : newRev;
        connected = true;
        connecting = false;
        status = "已连接";
        callback.onSessionChanged(this);
        callback.onStateChanged(this);
    }

    @Override
    public void onPairFailed(String message) {
        connecting = false;
        connected = false;
        status = FriendlyError.translate(message);
        lastError = status;
        callback.onSessionChanged(this);
        callback.onPairFailed(this, status);
    }

    @Override
    public void onDisconnected(String message) {
        connected = false;
        connecting = false;
        status = FriendlyError.translate(message);
        lastError = status;
        callback.onSessionChanged(this);
    }

    @Override
    public void onScheduleState(JSONObject newState, String newRev) {
        state = newState == null ? new JSONObject() : newState;
        rev = newRev == null ? "" : newRev;
        callback.onStateChanged(this);
    }

    @Override
    public void onScheduleSaved(String newRev) {
        rev = newRev == null ? "" : newRev;
        callback.onScheduleSaved(this, rev);
    }

    @Override
    public void onScheduleConflict(JSONObject current, String currentRev, String message) {
        callback.onConflict(this, current, currentRev, message);
    }

    @Override
    public void onScheduleChanged(String newRev) {
        callback.onRemoteChanged(this, newRev == null ? "" : newRev);
    }

    @Override
    public void onNotifyResult(boolean ok, String message) {
        callback.onNotifyResult(this, ok, message);
    }

    @Override
    public void onUnpairOk() {
        connected = false;
        status = "已解除配对";
        callback.onSessionChanged(this);
    }

    @Override
    public void onError(String message) {
        status = FriendlyError.translate(message);
        lastError = status;
        callback.onSessionChanged(this);
    }
}
