package com.miaoruixuan.zxremote;

import android.app.Activity;
import android.app.Dialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class MainActivity extends Activity {
    private Store store;
    private Ui ui;
    private DeviceManager manager;
    private FrameLayout root;
    private View connectView;
    private HomePage homePage;
    private FrameLayout detailHost;
    private final Map<String, DeviceDetailPage> detailPages = new HashMap<>();
    private DeviceDetailPage currentDetail;
    private LinearLayout hostList;
    private EditText deviceNameEdit;
    private EditText manualEdit;
    private TextView connectStatus;
    private final List<HostItem> hostItems = new ArrayList<>();
    private final List<Discovered> discovered = new ArrayList<>();
    private HostItem selectedHost;
    private String selectedKey = "";
    private boolean scanning = false;
    private final Map<String, Boolean> groupPending = new HashMap<>();
    private int groupOk = 0;
    private int groupFail = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        store = new Store(this);
        ui = new Ui(this, themeDark());
        ui.applyWindow(this);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);
        manager = new DeviceManager(store, new ManagerListener());
        build();
        manager.load();
        if (manager.sessions().isEmpty()) {
            showConnect();
        } else {
            showHome();
            manager.connectAll();
        }
    }

    private boolean themeDark() {
        String mode = store.theme();
        if ("dark".equals(mode)) {
            return true;
        }
        if ("light".equals(mode)) {
            return false;
        }
        return Ui.systemDark(this);
    }

    private void build() {
        root = new FrameLayout(this);
        root.setBackgroundColor(ui.bg);
        connectView = buildConnect();
        homePage = new HomePage(this, ui, new HomeListener());
        detailHost = new FrameLayout(this);
        root.addView(connectView, match());
        root.addView(homePage, match());
        root.addView(detailHost, match());
        connectView.setVisibility(View.GONE);
        homePage.setVisibility(View.GONE);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            int top = 0;
            int bottom = 0;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                top = bars.top;
                bottom = bars.bottom;
            } else {
                top = insets.getSystemWindowInsetTop();
                bottom = insets.getSystemWindowInsetBottom();
            }
            view.setPadding(0, top, 0, bottom);
            return insets;
        });
        root.requestApplyInsets();
        setContentView(root);
    }

    private FrameLayout.LayoutParams match() {
        return new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT);
    }

    private View buildConnect() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(ui.bg);
        LinearLayout page = ui.vertical();
        page.setPadding(ui.dp(20), ui.dp(14), ui.dp(20), ui.dp(20));
        scroll.addView(page, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));
        LinearLayout top = ui.horizontal();
        TextView title = ui.label("添加设备", 22, ui.text, true);
        top.addView(title, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        Button settings = ui.smallButton("设置");
        settings.setOnClickListener(view -> showSettings());
        top.addView(settings);
        page.addView(top);
        page.addView(ui.label("在 ZX 设置页“远程”中启用并生成配对码，然后在这里连接。",
                12, ui.dim, false), topMargin(4));

        LinearLayout nameRow = ui.horizontal();
        nameRow.addView(ui.label("设备名称", 12, ui.dim, false));
        deviceNameEdit = ui.input("设备名称", false);
        deviceNameEdit.setText(store.deviceName());
        LinearLayout.LayoutParams nameParams = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        nameParams.leftMargin = ui.dp(8);
        nameRow.addView(deviceNameEdit, nameParams);
        page.addView(nameRow, topMargin(14));

        LinearLayout card = ui.card();
        card.addView(ui.label("可用设备", 14, ui.text, true));
        hostList = ui.vertical();
        card.addView(hostList, topMargin(8));
        page.addView(card, topMargin(12));

        LinearLayout actions = ui.horizontal();
        Button scan = ui.button("扫描局域网", false);
        scan.setOnClickListener(view -> scan());
        actions.addView(scan);
        Button connect = ui.button("连接选中", true);
        connect.setOnClickListener(view -> connectSelected());
        actions.addView(connect, marginLeft(8));
        page.addView(actions, topMargin(10));
        connectStatus = ui.label("准备扫描", 12, ui.dim, false);
        page.addView(connectStatus, topMargin(8));

        LinearLayout manualRow = ui.horizontal();
        manualRow.addView(ui.label("手动地址", 12, ui.dim, false));
        manualEdit = ui.input("例如 192.168.1.5:48700", false);
        LinearLayout.LayoutParams manualParams = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        manualParams.leftMargin = ui.dp(8);
        manualRow.addView(manualEdit, manualParams);
        Button manual = ui.button("连接", false);
        manual.setOnClickListener(view -> connectManual());
        manualRow.addView(manual, marginLeft(8));
        page.addView(manualRow, topMargin(12));
        page.addView(ui.label("配对码 5 分钟内有效，每台设备只需配对一次。可同时配对多台电脑。",
                11, ui.dim, false), topMargin(12));
        return scroll;
    }

    private LinearLayout.LayoutParams marginLeft(int value) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.leftMargin = ui.dp(value);
        return params;
    }

    private LinearLayout.LayoutParams topMargin(int value) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = ui.dp(value);
        return params;
    }

    private void scan() {
        scanning = true;
        discovered.clear();
        rebuildHostList();
        connectStatus.setText("正在扫描局域网…");
        Protocol.scan(1800, new Protocol.DiscoveryListener() {
            @Override
            public void onFound(JSONObject host, String address, int port) {
                runOnUiThread(() -> {
                    discovered.add(new Discovered(host, address, port));
                    refreshHostItems();
                    rebuildHostList();
                });
            }

            @Override
            public void onFinished() {
                runOnUiThread(() -> {
                    scanning = false;
                    refreshHostItems();
                    rebuildHostList();
                    connectStatus.setText("扫描完成，发现 " + hostItems.size() + " 台设备");
                });
            }

            @Override
            public void onError(String message) {
                runOnUiThread(() -> {
                    scanning = false;
                    connectStatus.setText(message == null ? "扫描失败" : message);
                });
            }
        });
    }

    private void refreshHostItems() {
        String keep = selectedKey;
        hostItems.clear();
        Set<String> savedIds = new HashSet<>();
        for (DeviceSession session : manager.sessions()) {
            HostItem item = new HostItem();
            item.saved = true;
            item.id = session.hostId;
            item.name = session.displayName();
            item.address = session.address;
            item.port = session.port;
            item.token = session.token;
            item.session = session;
            for (Discovered value : discovered) {
                if (value.host.optString("id", "").equals(item.id)) {
                    item.address = value.address;
                    item.port = value.port;
                }
            }
            if (!item.id.isEmpty() && !item.token.isEmpty()) {
                savedIds.add(item.id);
                hostItems.add(item);
            }
        }
        Set<String> seen = new HashSet<>();
        for (Discovered value : discovered) {
            String id = value.host.optString("id", "");
            if (savedIds.contains(id) || seen.contains(id)) {
                continue;
            }
            seen.add(id);
            HostItem item = new HostItem();
            item.id = id;
            item.name = value.host.optString("name", "ZX");
            item.address = value.address;
            item.port = value.port;
            hostItems.add(item);
        }
        selectedHost = null;
        for (HostItem item : hostItems) {
            if (!keep.isEmpty() && item.key().equals(keep)) {
                selectedHost = item;
            }
        }
    }

    private void rebuildHostList() {
        hostList.removeAllViews();
        if (hostItems.isEmpty()) {
            hostList.addView(ui.label(scanning ? "正在扫描…" : "暂未发现设备，可扫描或手动输入地址",
                    12, ui.dim, false));
            return;
        }
        for (HostItem item : hostItems) {
            LinearLayout row = ui.vertical();
            row.setPadding(ui.dp(10), ui.dp(9), ui.dp(10), ui.dp(9));
            boolean active = selectedHost != null && selectedHost.key().equals(item.key());
            row.setBackground(active ? ui.roundStroke(ui.panel2, 8, ui.accent, 1)
                    : ui.roundStroke(ui.panel2, 8, ui.border, 1));
            row.addView(ui.label(item.name + (item.saved ? " · 已配对" : " · 未配对"),
                    14, ui.text, true));
            String state = item.session == null ? "未配对" : item.session.status;
            row.addView(ui.label(item.address + ":" + item.port + " · " + state,
                    11, ui.dim, false));
            row.setOnClickListener(view -> {
                selectedHost = item;
                selectedKey = item.key();
                rebuildHostList();
            });
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            params.topMargin = ui.dp(6);
            hostList.addView(row, params);
        }
    }

    private void connectSelected() {
        if (selectedHost == null) {
            connectStatus.setText("请先选择一个设备");
            return;
        }
        if (selectedHost.saved && selectedHost.session != null) {
            selectedHost.session.connect();
            showHome();
            return;
        }
        showPairDialog(selectedHost);
    }

    private void showPairDialog(HostItem item) {
        LinearLayout form = ui.vertical();
        form.addView(ui.label(item.address + ":" + item.port, 11, ui.dim, false));
        EditText code = ui.input("6 位配对码", false);
        code.setTextSize(22);
        code.setGravity(Gravity.CENTER);
        code.setInputType(InputType.TYPE_CLASS_NUMBER);
        EditText name = ui.input("设备名称", false);
        name.setText(store.deviceName());
        form.addView(ui.label("配对码", 11, ui.dim, false), topMargin(8));
        form.addView(code);
        form.addView(ui.label("设备名称", 11, ui.dim, false), topMargin(8));
        form.addView(name);
        final Dialog[] holder = new Dialog[1];
        holder[0] = ui.dialog("与 " + item.name + " 配对", form, "取消", "确认配对", view -> {
            String value = code.getText().toString().trim();
            if (value.length() != 6) {
                Toast.makeText(this, "请输入 6 位配对码", Toast.LENGTH_SHORT).show();
                return;
            }
            String deviceName = name.getText().toString().trim();
            if (deviceName.isEmpty()) {
                Toast.makeText(this, "请输入设备名称", Toast.LENGTH_SHORT).show();
                return;
            }
            store.setDeviceName(deviceName);
            holder[0].dismiss();
            manager.pairNew(item.address, item.port, value);
            showHome();
        });
    }

    private void connectManual() {
        String text = manualEdit.getText().toString().trim();
        if (text.isEmpty()) {
            connectStatus.setText("请输入 IP:端口");
            return;
        }
        String address = text;
        int port = Version.DEFAULT_CONTROL_PORT;
        if (text.contains(":")) {
            int index = text.lastIndexOf(':');
            address = text.substring(0, index);
            try {
                port = Integer.parseInt(text.substring(index + 1));
            } catch (Exception exc) {
                connectStatus.setText("地址格式应为 IP:端口");
                return;
            }
        }
        HostItem item = new HostItem();
        item.id = "manual-" + address + "-" + port;
        item.name = "手动连接";
        item.address = address;
        item.port = port;
        selectedHost = item;
        selectedKey = item.key();
        rebuildHostList();
        showPairDialog(item);
    }

    private void showConnect() {
        connectView.setVisibility(View.VISIBLE);
        homePage.setVisibility(View.GONE);
        detailHost.setVisibility(View.GONE);
        currentDetail = null;
        refreshHostItems();
        rebuildHostList();
    }

    private void showHome() {
        connectView.setVisibility(View.GONE);
        homePage.setVisibility(View.VISIBLE);
        detailHost.setVisibility(View.GONE);
        currentDetail = null;
        homePage.setSessions(manager.sessions());
    }

    private void openDetail(DeviceSession session) {
        String key = session.key();
        DeviceDetailPage page = detailPages.get(key);
        if (page == null) {
            page = new DeviceDetailPage(this, ui, store, new DetailListener());
            detailPages.put(key, page);
            detailHost.addView(page, match());
        }
        for (int index = 0; index < detailHost.getChildCount(); index++) {
            View child = detailHost.getChildAt(index);
            child.setVisibility(child == page ? View.VISIBLE : View.GONE);
        }
        currentDetail = page;
        page.setSession(session);
        connectView.setVisibility(View.GONE);
        homePage.setVisibility(View.GONE);
        detailHost.setVisibility(View.VISIBLE);
    }

    private void closeDetail(DeviceSession session) {
        String key = session.key();
        DeviceDetailPage page = detailPages.remove(key);
        if (page != null) {
            detailHost.removeView(page);
        }
        if (currentDetail == page) {
            currentDetail = null;
        }
    }

    private void confirm(String message, Runnable action) {
        LinearLayout panel = ui.vertical();
        panel.addView(ui.label(message, 13, ui.text, false));
        final Dialog[] holder = new Dialog[1];
        holder[0] = ui.dialog("确认", panel, "取消", "继续", view -> {
            holder[0].dismiss();
            action.run();
        });
    }

    private void showSettings() {
        LinearLayout content = ui.vertical();
        content.addView(ui.label("ZX 控制台 v" + Version.VERSION + " · 构建 " +
                Version.BUILD_VERSION, 12, ui.dim, false));
        content.addView(ui.label("外观", 13, ui.text, true), topMargin(12));
        LinearLayout themes = ui.horizontal();
        String current = store.theme();
        String[] modes = {"system", "dark", "light"};
        String[] labels = {"跟随系统", "深色", "浅色"};
        for (int index = 0; index < modes.length; index++) {
            Button button = ui.smallButton(labels[index]);
            if (modes[index].equals(current)) {
                button.setTextColor(ui.accent);
            }
            final String mode = modes[index];
            button.setOnClickListener(view -> {
                store.setTheme(mode);
                recreate();
            });
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            params.leftMargin = ui.dp(index == 0 ? 0 : 6);
            themes.addView(button, params);
        }
        content.addView(themes, topMargin(6));
        content.addView(ui.label("项目主页", 13, ui.text, true), topMargin(14));
        TextView gitee = ui.label("Gitee · gitee.com/guzhi233/countdown---djs",
                12, ui.accent, false);
        gitee.setOnClickListener(view ->
                openProjectLink("https://gitee.com/guzhi233/countdown---djs"));
        content.addView(gitee, topMargin(4));
        TextView github = ui.label("GitHub · github.com/GuZhi-233/Countdown-DJS",
                12, ui.accent, false);
        github.setOnClickListener(view ->
                openProjectLink("https://github.com/GuZhi-233/Countdown-DJS"));
        content.addView(github, topMargin(2));
        content.addView(ui.label("使用说明", 13, ui.text, true), topMargin(14));
        content.addView(ui.label("1. 电脑端 ZX 设置页“远程”中启用并生成配对码。", 12, ui.dim, false),
                topMargin(4));
        content.addView(ui.label("2. 在“添加设备”中扫描或手动输入电脑地址并完成配对。", 12, ui.dim, false),
                topMargin(2));
        content.addView(ui.label("3. 已配对设备会出现在主页，启动时自动尝试连接。", 12, ui.dim, false),
                topMargin(2));
        content.addView(ui.label("4. 主页勾选多台设备可群发教师通知，进入详情可单独发送。",
                12, ui.dim, false), topMargin(2));
        content.addView(ui.label("已配对设备：" + manager.sessions().size() + " 台",
                12, ui.dim, false), topMargin(12));
        Button clean = ui.smallButton("清理失效配对");
        clean.setTextColor(ui.danger);
        clean.setOnClickListener(view -> {
            int removed = manager.removeInvalid();
            Toast.makeText(this, removed > 0 ? "已清理 " + removed + " 台" : "没有失效配对",
                    Toast.LENGTH_SHORT).show();
        });
        content.addView(clean, topMargin(6));
        ui.dialog("设置", content, "关闭", "", null);
    }

    private void openProjectLink(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception exc) {
            Toast.makeText(this, "无法打开浏览器", Toast.LENGTH_SHORT).show();
        }
    }

    private void startGroupNotify(List<DeviceSession> targets) {
        GroupNotifyDialog.show(this, ui, targets, (title, body, duration) -> {
            groupPending.clear();
            groupOk = 0;
            groupFail = 0;
            for (DeviceSession session : targets) {
                groupPending.put(session.key(), false);
                session.sendNotify(title, body, duration);
            }
            Toast.makeText(this, "正在发送到 " + targets.size() + " 台设备…",
                    Toast.LENGTH_SHORT).show();
            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                if (!groupPending.isEmpty()) {
                    int pending = groupPending.size();
                    groupPending.clear();
                    Toast.makeText(this, "部分设备未响应：" + pending + " 台",
                            Toast.LENGTH_LONG).show();
                }
            }, 6000);
        });
    }

    private void hideKeyboard() {
        try {
            InputMethodManager manager = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
            View focus = getCurrentFocus();
            if (manager != null && focus != null) {
                manager.hideSoftInputFromWindow(focus.getWindowToken(), 0);
            }
        } catch (Exception ignored) {
        }
    }

    private class ManagerListener implements DeviceManager.Listener {
        @Override
        public void onSessionsChanged() {
            runOnUiThread(() -> {
                homePage.setSessions(manager.sessions());
                if (currentDetail != null && manager.find(currentDetail.session() == null
                        ? "" : currentDetail.session().hostId) == null) {
                    showHome();
                }
                if (connectView.getVisibility() == View.VISIBLE) {
                    refreshHostItems();
                    rebuildHostList();
                }
            });
        }

        @Override
        public void onSessionChanged(DeviceSession session) {
            runOnUiThread(() -> {
                homePage.setSessions(manager.sessions());
                if (currentDetail != null && currentDetail.session() == session) {
                    currentDetail.onSessionChanged(session);
                }
                if (connectView.getVisibility() == View.VISIBLE) {
                    refreshHostItems();
                    rebuildHostList();
                }
            });
        }

        @Override
        public void onPaired(DeviceSession session) {
            runOnUiThread(() -> {
                hideKeyboard();
                showHome();
                Toast.makeText(MainActivity.this, "配对成功", Toast.LENGTH_SHORT).show();
            });
        }

        @Override
        public void onStateChanged(DeviceSession session) {
            runOnUiThread(() -> {
                if (currentDetail != null && currentDetail.session() == session) {
                    currentDetail.onStateChanged(session);
                }
            });
        }

        @Override
        public void onScheduleSaved(DeviceSession session, String rev) {
            runOnUiThread(() -> {
                if (currentDetail != null && currentDetail.session() == session) {
                    currentDetail.onScheduleSaved(session, rev);
                }
                Toast.makeText(MainActivity.this, "课表已保存到 " + session.displayName(),
                        Toast.LENGTH_SHORT).show();
            });
        }

        @Override
        public void onConflict(DeviceSession session, JSONObject state, String rev, String message) {
            runOnUiThread(() -> {
                if (currentDetail != null && currentDetail.session() == session) {
                    currentDetail.onConflict(session, state, rev, message);
                }
            });
        }

        @Override
        public void onNotifyResult(DeviceSession session, boolean ok, String message) {
            runOnUiThread(() -> {
                if (currentDetail != null && currentDetail.session() == session) {
                    currentDetail.onNotifyResult(session, ok, message);
                }
                if (groupPending.containsKey(session.key())) {
                    groupPending.remove(session.key());
                    if (ok) {
                        groupOk += 1;
                    } else {
                        groupFail += 1;
                    }
                    if (groupPending.isEmpty()) {
                        Toast.makeText(MainActivity.this,
                                "发送完成：成功 " + groupOk + " 台，失败 " + groupFail + " 台",
                                Toast.LENGTH_LONG).show();
                    }
                }
            });
        }

        @Override
        public void onPairFailed(DeviceSession session, String message) {
            runOnUiThread(() -> {
                if (connectStatus != null) {
                    connectStatus.setText(message == null ? "配对失败" : message);
                }
                Toast.makeText(MainActivity.this, message == null ? "配对失败" : message,
                        Toast.LENGTH_LONG).show();
                refreshHostItems();
                rebuildHostList();
                if (manager.sessions().isEmpty()) {
                    showConnect();
                }
            });
        }

        @Override
        public void onRemoteChanged(DeviceSession session, String rev) {
            runOnUiThread(() -> {
                if (currentDetail != null && currentDetail.session() == session) {
                    currentDetail.onRemoteChanged(session, rev);
                } else if (!rev.equals(session.rev)) {
                    session.requestSchedule();
                }
            });
        }
    }

    private class HomeListener implements HomePage.Listener {
        @Override
        public void onOpenDevice(DeviceSession session) {
            openDetail(session);
        }

        @Override
        public void onAddDevice() {
            showConnect();
        }

        @Override
        public void onSettings() {
            showSettings();
        }

        @Override
        public void onGroupNotify(List<DeviceSession> targets) {
            startGroupNotify(targets);
        }
    }

    private class DetailListener implements DeviceDetailPage.Callback {
        @Override
        public void onBack() {
            showHome();
        }

        @Override
        public void onSettings() {
            showSettings();
        }

        @Override
        public void onReconnect(DeviceSession session) {
            session.connect();
            if (currentDetail != null) {
                currentDetail.onSessionChanged(session);
            }
        }

        @Override
        public void onUnpair(DeviceSession session) {
            confirm("解除配对会通知电脑端移除本机，继续？", () -> {
                if (session.isConnected()) {
                    session.unpair();
                    new Handler(Looper.getMainLooper()).postDelayed(() -> {
                        closeDetail(session);
                        manager.remove(session, false);
                        showHome();
                    }, 400);
                } else {
                    closeDetail(session);
                    manager.remove(session, false);
                    showHome();
                }
            });
        }

        @Override
        public void onRemove(DeviceSession session) {
            confirm("移除设备只删除手机上的记录，继续？", () -> {
                closeDetail(session);
                manager.remove(session, false);
                showHome();
            });
        }

        @Override
        public void onAlias(DeviceSession session, String alias) {
            session.setAlias(alias);
            Toast.makeText(MainActivity.this, "备注已保存", Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    public void onBackPressed() {
        if (detailHost.getVisibility() == View.VISIBLE) {
            showHome();
            return;
        }
        if (homePage.getVisibility() == View.VISIBLE) {
            super.onBackPressed();
            return;
        }
        if (!manager.sessions().isEmpty()) {
            showHome();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (manager != null) {
            manager.closeAll();
        }
        super.onDestroy();
    }

    private static final class HostItem {
        String id = "";
        String name = "ZX";
        String address = "";
        int port = Version.DEFAULT_CONTROL_PORT;
        String token = "";
        boolean saved = false;
        DeviceSession session;

        String key() {
            return id + "|" + address + "|" + port;
        }
    }

    private static final class Discovered {
        final JSONObject host;
        final String address;
        final int port;

        Discovered(JSONObject host, String address, int port) {
            this.host = host == null ? new JSONObject() : host;
            this.address = address;
            this.port = port;
        }
    }
}
