package com.miaoruixuan.zxremote;

import org.json.JSONObject;

import android.util.Log;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class Protocol {
    private Protocol() {
    }

    public static final class Client {
        public interface Listener {
            void onPaired(JSONObject host, JSONObject state, String rev, String token);

            void onConnected(JSONObject host, JSONObject state, String rev);

            void onPairFailed(String message);

            void onDisconnected(String message);

            void onScheduleState(JSONObject state, String rev);

            void onScheduleSaved(String rev);

            void onScheduleConflict(JSONObject state, String rev, String message);

            void onScheduleChanged(String rev);

            void onNotifyResult(boolean ok, String message);

            void onUnpairOk();

            void onError(String message);
        }

        private final Listener listener;
        private final Object writeLock = new Object();
        private Socket socket;
        private DataInputStream input;
        private DataOutputStream output;
        private Thread heartbeat;
        private volatile boolean closed;
        private volatile boolean authed;

        public Client(Listener listener) {
            this.listener = listener;
        }

        public void pair(String address, int port, String code, String deviceId,
                         String deviceName, String appVersion) {
            JSONObject request = new JSONObject();
            try {
                request.put("type", "pair_request");
                request.put("code", code);
                JSONObject device = new JSONObject();
                device.put("id", deviceId);
                device.put("name", deviceName);
                device.put("platform", "android");
                request.put("device", device);
                request.put("app_version", appVersion);
            } catch (Exception ignored) {
            }
            start(address, port, request);
        }

        public void hello(String address, int port, String deviceId, String token,
                          String appVersion) {
            JSONObject request = new JSONObject();
            try {
                request.put("type", "hello");
                request.put("device_id", deviceId);
                request.put("token", token);
                request.put("app_version", appVersion);
            } catch (Exception ignored) {
            }
            start(address, port, request);
        }

        private void start(String address, int port, JSONObject hello) {
            close();
            closed = false;
            authed = false;
            Thread thread = new Thread(() -> {
                boolean reported = false;
                try {
                    Socket target = new Socket();
                    target.connect(new InetSocketAddress(address, port), 5000);
                    target.setSoTimeout(90000);
                    socket = target;
                    input = new DataInputStream(target.getInputStream());
                    output = new DataOutputStream(target.getOutputStream());
                    startHeartbeat();
                    sendNow(hello);
                    while (!closed) {
                        int length;
                        try {
                            length = input.readInt();
                        } catch (EOFException eof) {
                            break;
                        }
                        if (length <= 0 || length > 1048576) {
                            throw new IOException("数据长度异常");
                        }
                        byte[] data = new byte[length];
                        input.readFully(data);
                        JSONObject message = new JSONObject(new String(data, StandardCharsets.UTF_8));
                        handle(message);
                    }
                } catch (Exception exc) {
                    if (!closed) {
                        reported = true;
                        failMessage(exc);
                    }
                } finally {
                    boolean wasClosed = closed;
                    closed = true;
                    closeQuietly();
                    if (!wasClosed && !reported) {
                        if (authed) {
                            authed = false;
                            listener.onDisconnected("与电脑端的连接已断开");
                        } else {
                            listener.onPairFailed("连接已断开，配对未完成");
                        }
                    }
                }
            }, "zx-remote-client");
            thread.setDaemon(true);
            thread.start();
        }

        private void failMessage(Exception exc) {
            String message = exc == null ? "" : exc.getMessage();
            if (message == null || message.isEmpty()) {
                message = "无法连接到电脑端";
            }
            String lower = message.toLowerCase();
            if (lower.contains("timed out") || lower.contains("timeout")) {
                message = "连接超时，请检查电脑端地址与防火墙";
            }
            Log.i("ZXRemote", "fail " + message);
            if (authed) {
                authed = false;
                listener.onDisconnected(message);
            } else {
                listener.onPairFailed(message);
            }
        }

        private void markAuthed() {
            authed = true;
            try {
                if (socket != null) {
                    socket.setSoTimeout(0);
                }
            } catch (Exception ignored) {
            }
        }

        private void startHeartbeat() {
            stopHeartbeat();
            heartbeat = new Thread(() -> {
                while (!closed) {
                    try {
                        Thread.sleep(20000);
                    } catch (InterruptedException exc) {
                        return;
                    }
                    if (closed) {
                        return;
                    }
                    if (authed) {
                        JSONObject ping = new JSONObject();
                        try {
                            ping.put("type", "ping");
                            ping.put("ts", System.currentTimeMillis() / 1000);
                        } catch (Exception ignored) {
                        }
                        sendNow(ping);
                    }
                }
            }, "zx-remote-heartbeat");
            heartbeat.setDaemon(true);
            heartbeat.start();
        }

        private void stopHeartbeat() {
            if (heartbeat != null) {
                heartbeat.interrupt();
                heartbeat = null;
            }
        }

        private void handle(JSONObject message) {
            String type = message.optString("type", "");
            Log.i("ZXRemote", "recv " + type);
            if ("pair_ok".equals(type)) {
                markAuthed();
                listener.onPaired(message.optJSONObject("host"), message.optJSONObject("state"),
                        message.optString("rev", ""), message.optString("token", ""));
            } else if ("pair_reject".equals(type)) {
                listener.onPairFailed(message.optString("reason", "配对失败"));
                close();
            } else if ("hello_ok".equals(type)) {
                markAuthed();
                listener.onConnected(message.optJSONObject("host"), message.optJSONObject("state"),
                        message.optString("rev", ""));
            } else if ("hello_fail".equals(type)) {
                listener.onPairFailed(message.optString("reason", "配对已失效"));
                close();
            } else if ("notify_ok".equals(type)) {
                listener.onNotifyResult(true, "");
            } else if ("schedule_state".equals(type)) {
                listener.onScheduleState(message.optJSONObject("state"), message.optString("rev", ""));
            } else if ("schedule_saved".equals(type)) {
                listener.onScheduleSaved(message.optString("rev", ""));
            } else if ("schedule_conflict".equals(type)) {
                listener.onScheduleConflict(message.optJSONObject("state"),
                        message.optString("rev", ""), message.optString("message", "课表已被修改"));
            } else if ("schedule_changed".equals(type)) {
                listener.onScheduleChanged(message.optString("rev", ""));
            } else if ("unpair_ok".equals(type)) {
                listener.onUnpairOk();
                close();
            } else if ("error".equals(type)) {
                listener.onError(message.optString("message", "操作失败"));
            }
        }

        private boolean send(JSONObject payload) {
            DataOutputStream target = output;
            if (target == null) {
                Log.i("ZXRemote", "send skipped " + payload.optString("type", ""));
                return false;
            }
            final byte[] data = payload.toString().getBytes(StandardCharsets.UTF_8);
            final String type = payload.optString("type", "");
            Thread writer = new Thread(() -> {
                synchronized (writeLock) {
                    try {
                        target.writeInt(data.length);
                        target.write(data);
                        target.flush();
                        Log.i("ZXRemote", "send ok " + type + " bytes=" + data.length);
                    } catch (Exception exc) {
                        Log.i("ZXRemote", "send fail " + type + " " + exc);
                    }
                }
            }, "zx-remote-send");
            writer.setDaemon(true);
            writer.start();
            return true;
        }

        private boolean sendNow(JSONObject payload) {
            DataOutputStream target = output;
            if (target == null) {
                Log.i("ZXRemote", "send skipped " + payload.optString("type", ""));
                return false;
            }
            try {
                byte[] data = payload.toString().getBytes(StandardCharsets.UTF_8);
                synchronized (writeLock) {
                    target.writeInt(data.length);
                    target.write(data);
                    target.flush();
                }
                Log.i("ZXRemote", "send ok " + payload.optString("type", "") +
                        " bytes=" + data.length);
                return true;
            } catch (Exception exc) {
                Log.i("ZXRemote", "send fail " + payload.optString("type", "") +
                        " " + exc);
                return false;
            }
        }

        public boolean isConnected() {
            return authed && socket != null && socket.isConnected() && !socket.isClosed();
        }

        public void requestSchedule() {
            JSONObject request = new JSONObject();
            try {
                request.put("type", "schedule_get");
            } catch (Exception ignored) {
            }
            send(request);
        }

        public void saveSchedule(JSONObject state, String rev, boolean force) {
            JSONObject request = new JSONObject();
            try {
                request.put("type", "schedule_put");
                request.put("base_rev", rev == null ? "" : rev);
                request.put("state", state);
                request.put("force", force);
            } catch (Exception ignored) {
            }
            send(request);
        }

        public void sendNotify(String mode, String title, String body, float duration) {
            JSONObject request = new JSONObject();
            try {
                request.put("type", "notify");
                request.put("mode", mode);
                request.put("title", title);
                request.put("body", body);
                request.put("duration", duration);
            } catch (Exception ignored) {
            }
            send(request);
        }

        public void unpair() {
            JSONObject request = new JSONObject();
            try {
                request.put("type", "unpair");
            } catch (Exception ignored) {
            }
            send(request);
        }

        public void close() {
            closed = true;
            closeQuietly();
        }

        private void closeQuietly() {
            stopHeartbeat();
            try {
                if (socket != null) {
                    socket.close();
                }
            } catch (Exception ignored) {
            }
            socket = null;
            input = null;
            output = null;
        }
    }

    public interface DiscoveryListener {
        void onFound(JSONObject host, String address, int port);

        void onFinished();

        void onError(String message);
    }

    public static void scan(int durationMillis, DiscoveryListener listener) {
        Thread thread = new Thread(() -> {
            DatagramSocket socket = null;
            try {
                socket = new DatagramSocket();
                socket.setBroadcast(true);
                socket.setSoTimeout(250);
                byte[] probe = "{\"zx_remote\":1,\"probe\":1}".getBytes(StandardCharsets.UTF_8);
                for (InetAddress target : broadcastAddresses()) {
                    try {
                        socket.send(new DatagramPacket(probe, probe.length, target,
                                Version.DISCOVERY_PORT));
                    } catch (Exception ignored) {
                    }
                }
                long deadline = System.currentTimeMillis() + Math.max(600, durationMillis);
                Set<String> seen = new HashSet<>();
                byte[] buffer = new byte[8192];
                while (System.currentTimeMillis() < deadline) {
                    try {
                        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                        socket.receive(packet);
                        String raw = new String(packet.getData(), 0, packet.getLength(),
                                StandardCharsets.UTF_8);
                        JSONObject payload = new JSONObject(raw);
                        if (payload.optInt("zx_remote", 0) != 1) {
                            continue;
                        }
                        JSONObject host = payload.optJSONObject("host");
                        int port = payload.optInt("port", 0);
                        if (host == null || port <= 0) {
                            continue;
                        }
                        String address = packet.getAddress().getHostAddress();
                        String key = host.optString("id", "") + "|" + address + "|" + port;
                        if (!seen.add(key)) {
                            continue;
                        }
                        listener.onFound(host, address, port);
                    } catch (SocketTimeoutException timeout) {
                        continue;
                    } catch (Exception ignored) {
                    }
                }
                listener.onFinished();
            } catch (Exception exc) {
                listener.onError(exc.getMessage() == null ? "扫描失败" : exc.getMessage());
            } finally {
                if (socket != null) {
                    socket.close();
                }
            }
        }, "zx-remote-discovery");
        thread.setDaemon(true);
        thread.start();
    }

    private static List<InetAddress> broadcastAddresses() {
        List<InetAddress> rows = new ArrayList<>();
        try {
            rows.add(InetAddress.getByName("255.255.255.255"));
        } catch (Exception ignored) {
        }
        try {
            for (NetworkInterface network : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!network.isUp() || network.isLoopback()) {
                    continue;
                }
                for (InterfaceAddress address : network.getInterfaceAddresses()) {
                    InetAddress broadcast = address.getBroadcast();
                    if (broadcast != null && !rows.contains(broadcast)) {
                        rows.add(broadcast);
                    }
                }
            }
        } catch (Exception ignored) {
        }
        return rows;
    }
}
