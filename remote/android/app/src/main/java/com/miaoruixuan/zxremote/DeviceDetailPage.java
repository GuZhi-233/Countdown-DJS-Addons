package com.miaoruixuan.zxremote;

import android.app.Dialog;
import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

public final class DeviceDetailPage extends LinearLayout {
    public interface Callback {
        void onBack();

        void onSettings();

        void onReconnect(DeviceSession session);

        void onUnpair(DeviceSession session);

        void onRemove(DeviceSession session);

        void onAlias(DeviceSession session, String alias);
    }

    private final Ui ui;
    private final Store store;
    private final Callback callback;
    private final TextView hostLabel;
    private final TextView stateLabel;
    private final Button[] tabs = new Button[3];
    private final FrameLayout content;
    private final SchedulePage schedule;
    private final NotifyPage notify;
    private final DevicePage device;
    private DeviceSession session;
    private String lastNotifyTitle = "教师通知";

    public DeviceDetailPage(Context context, Ui ui, Store store, Callback callback) {
        super(context);
        this.ui = ui;
        this.store = store;
        this.callback = callback;
        setOrientation(VERTICAL);
        setBackgroundColor(ui.bg);

        LinearLayout top = ui.horizontal();
        top.setPadding(ui.dp(10), ui.dp(8), ui.dp(12), ui.dp(6));
        Button back = ui.smallButton("‹");
        back.setTextSize(22);
        back.setOnClickListener(view -> callback.onBack());
        top.addView(back);
        LinearLayout titleBox = ui.vertical();
        titleBox.setPadding(ui.dp(6), 0, 0, 0);
        hostLabel = ui.label("设备", 16, ui.text, true);
        stateLabel = ui.label("未连接", 11, ui.dim, false);
        titleBox.addView(hostLabel);
        titleBox.addView(stateLabel);
        top.addView(titleBox, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        Button settings = ui.smallButton("设置");
        settings.setOnClickListener(view -> callback.onSettings());
        top.addView(settings);
        addView(top);

        LinearLayout tabRow = ui.horizontal();
        tabRow.setPadding(ui.dp(10), 0, ui.dp(10), ui.dp(6));
        String[] names = {"课表", "教师通知", "设备"};
        for (int index = 0; index < names.length; index++) {
            final int value = index;
            Button button = new Button(context);
            button.setAllCaps(false);
            button.setText(names[index]);
            button.setTextSize(13);
            button.setMinHeight(0);
            button.setMinimumHeight(0);
            button.setOnClickListener(view -> showTab(value));
            tabs[index] = button;
            tabRow.addView(button, new LinearLayout.LayoutParams(0,
                    LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        }
        addView(tabRow);

        content = new FrameLayout(context);
        addView(content, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));

        schedule = new SchedulePage(context, ui, new SchedulePage.Callback() {
            @Override
            public void onDirty() {
                stateLabel.setText("有未保存修改");
                stateLabel.setTextColor(ui.danger);
            }

            @Override
            public void onSaveRequested() {
                if (session == null) {
                    return;
                }
                session.saveSchedule(schedule.state(), schedule.rev(), false);
                schedule.showStatus("正在保存…");
            }

            @Override
            public void onRefreshRequested() {
                if (session == null) {
                    return;
                }
                if (schedule.isDirty()) {
                    confirm("刷新会丢弃本地未保存的修改，继续？", () -> {
                        session.requestSchedule();
                        schedule.showStatus("正在刷新…");
                    });
                    return;
                }
                session.requestSchedule();
                schedule.showStatus("正在刷新…");
            }
        });
        final NotifyPage[] notifyHolder = new NotifyPage[1];
        notify = new NotifyPage(context, ui, (title, body, duration) -> {
            if (session == null || !session.isConnected()) {
                if (notifyHolder[0] != null) {
                    notifyHolder[0].onResult(false, "尚未连接电脑端");
                }
                return;
            }
            lastNotifyTitle = title;
            session.sendNotify(title, body, duration);
        });
        notifyHolder[0] = notify;
        device = new DevicePage(context, ui, new DevicePage.Callback() {
            @Override
            public void onReconnect(DeviceSession value) {
                callback.onReconnect(value);
            }

            @Override
            public void onUnpair(DeviceSession value) {
                callback.onUnpair(value);
            }

            @Override
            public void onRemove(DeviceSession value) {
                callback.onRemove(value);
            }

            @Override
            public void onAlias(DeviceSession value, String alias) {
                callback.onAlias(value, alias);
            }
        });
        content.addView(schedule, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        content.addView(notify, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        content.addView(device, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        showTab(0);
    }

    public void setSession(DeviceSession value) {
        session = value;
        applyStatus();
        if (session == null) {
            return;
        }
        schedule.setEnabled(session.isConnected());
        notify.setEnabled(session.isConnected());
        notify.setHistory(historyFor(session.hostId));
        if (!schedule.isDirty()) {
            schedule.setState(session.state, session.rev);
        }
    }

    public DeviceSession session() {
        return session;
    }

    public void onSessionChanged(DeviceSession value) {
        if (session != value) {
            return;
        }
        applyStatus();
        schedule.setEnabled(value.isConnected());
        notify.setEnabled(value.isConnected());
    }

    public void onStateChanged(DeviceSession value) {
        if (session != value) {
            return;
        }
        if (schedule.isDirty()) {
            schedule.showRemoteChanged();
            return;
        }
        schedule.setState(value.state, value.rev);
        applyStatus();
    }

    public void onScheduleSaved(DeviceSession value, String rev) {
        if (session != value) {
            return;
        }
        schedule.markSaved(rev);
        schedule.showStatus("已保存到 ZX");
    }

    public void onConflict(DeviceSession value, JSONObject state, String rev, String message) {
        if (session != value) {
            return;
        }
        LinearLayout panel = ui.vertical();
        panel.addView(ui.label(message == null ? "电脑端课表已变化" : message,
                13, ui.text, false));
        panel.addView(ui.label("重新加载会丢弃本地修改；覆盖会以本地版本替换电脑端课表。",
                11, ui.dim, false));
        Button reload = ui.button("重新加载", false);
        Button overwrite = ui.button("覆盖电脑端", true);
        LinearLayout actions = ui.horizontal();
        actions.addView(reload);
        LinearLayout.LayoutParams overwriteParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        overwriteParams.leftMargin = ui.dp(8);
        actions.addView(overwrite, overwriteParams);
        LinearLayout.LayoutParams actionParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        actionParams.topMargin = ui.dp(10);
        panel.addView(actions, actionParams);
        final Dialog[] holder = new Dialog[1];
        holder[0] = ui.dialog("课表冲突", panel, "取消", "", null);
        reload.setOnClickListener(view -> {
            holder[0].dismiss();
            schedule.discardDirty();
            session.requestSchedule();
        });
        overwrite.setOnClickListener(view -> {
            holder[0].dismiss();
            session.saveSchedule(schedule.state(), schedule.rev(), true);
            schedule.showStatus("正在覆盖…");
        });
    }

    public void onNotifyResult(DeviceSession value, boolean ok, String message) {
        if (session != value) {
            return;
        }
        notify.onResult(ok, message);
        if (ok) {
            JSONObject entry = new JSONObject();
            put(entry, "ts", System.currentTimeMillis() / 1000);
            put(entry, "mode", "quick");
            put(entry, "title", lastNotifyTitle);
            put(entry, "hostId", session.hostId);
            put(entry, "hostName", session.displayName());
            store.addHistory(entry);
            notify.setHistory(historyFor(session.hostId));
        }
    }

    public void onRemoteChanged(DeviceSession value, String rev) {
        if (session != value) {
            return;
        }
        if (schedule.isDirty()) {
            schedule.showRemoteChanged();
            return;
        }
        if (!rev.equals(schedule.rev())) {
            session.requestSchedule();
        }
    }

    private void applyStatus() {
        if (session == null) {
            return;
        }
        hostLabel.setText(session.displayName());
        stateLabel.setText(session.status);
        stateLabel.setTextColor(session.isConnected() ? ui.success
                : (session.connecting ? ui.accent : ui.danger));
        device.setSession(session);
    }

    private void showTab(int index) {
        schedule.setVisibility(index == 0 ? View.VISIBLE : View.GONE);
        notify.setVisibility(index == 1 ? View.VISIBLE : View.GONE);
        device.setVisibility(index == 2 ? View.VISIBLE : View.GONE);
        for (int position = 0; position < tabs.length; position++) {
            boolean active = position == index;
            tabs[position].setTextColor(active ? ui.accent : ui.dim);
            tabs[position].setBackground(active ? ui.roundStroke(ui.panel2, 8, ui.accent, 1)
                    : null);
        }
    }

    private JSONArray historyFor(String hostId) {
        JSONArray rows = store.history();
        JSONArray result = new JSONArray();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.optJSONObject(index);
            if (row != null && hostId.equals(row.optString("hostId", ""))) {
                add(result, row);
            }
        }
        return result;
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
