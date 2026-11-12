package com.miaoruixuan.zxremote;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class HomePage extends LinearLayout {
    public interface Listener {
        void onOpenDevice(DeviceSession session);

        void onAddDevice();

        void onSettings();

        void onGroupNotify(List<DeviceSession> targets);
    }

    private final Ui ui;
    private final Listener listener;
    private final Set<String> selected = new LinkedHashSet<>();
    private final List<DeviceSession> sessions = new ArrayList<>();
    private LinearLayout listBox;
    private TextView subtitle;
    private Button groupButton;

    public HomePage(Context context, Ui ui, Listener listener) {
        super(context);
        this.ui = ui;
        this.listener = listener;
        setOrientation(VERTICAL);
        setBackgroundColor(ui.bg);
        setPadding(ui.dp(14), ui.dp(10), ui.dp(14), ui.dp(10));
        build();
    }

    private void build() {
        LinearLayout top = ui.horizontal();
        TextView title = ui.label("ZX 控制台", 22, ui.text, true);
        top.addView(title, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        Button settings = ui.smallButton("设置");
        settings.setOnClickListener(view -> listener.onSettings());
        top.addView(settings);
        Button add = ui.smallButton("+");
        add.setOnClickListener(view -> listener.onAddDevice());
        LinearLayout.LayoutParams addParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        addParams.leftMargin = ui.dp(6);
        top.addView(add, addParams);
        addView(top);
        subtitle = ui.label("", 11, ui.dim, false);
        addView(subtitle, topMargin(2));

        ScrollView scroll = new ScrollView(getContext());
        scroll.setFillViewport(true);
        listBox = ui.vertical();
        listBox.setPadding(0, ui.dp(8), 0, ui.dp(8));
        scroll.addView(listBox, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));
        addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));

        groupButton = ui.button("发送教师通知（已选 0 台）", true);
        groupButton.setOnClickListener(view -> {
            List<DeviceSession> targets = selectedSessions();
            if (!targets.isEmpty()) {
                listener.onGroupNotify(targets);
            }
        });
        addView(groupButton);
    }

    private LinearLayout.LayoutParams topMargin(int value) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = ui.dp(value);
        return params;
    }

    public void setSessions(List<DeviceSession> values) {
        sessions.clear();
        if (values != null) {
            sessions.addAll(values);
        }
        Set<String> keys = new LinkedHashSet<>();
        for (DeviceSession session : sessions) {
            keys.add(session.key());
        }
        selected.retainAll(keys);
        rebuild();
    }

    private void rebuild() {
        listBox.removeAllViews();
        subtitle.setText("设备主页 · 已配对 " + sessions.size() + " 台");
        if (sessions.isEmpty()) {
            LinearLayout empty = ui.card();
            empty.addView(ui.label("还没有配对设备", 16, ui.text, true));
            empty.addView(ui.label("点击右上角“+”扫描局域网或手动输入电脑地址。",
                    12, ui.dim, false), topMargin(4));
            Button add = ui.button("添加设备", true);
            add.setOnClickListener(view -> listener.onAddDevice());
            LinearLayout.LayoutParams addParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            addParams.topMargin = ui.dp(10);
            empty.addView(add, addParams);
            listBox.addView(empty);
            updateGroupButton();
            return;
        }
        for (DeviceSession session : sessions) {
            LinearLayout card = ui.horizontal();
            card.setBackground(ui.roundStroke(ui.panel, 12, ui.border, 1));
            card.setPadding(ui.dp(10), ui.dp(10), ui.dp(12), ui.dp(10));
            CheckBox check = new CheckBox(getContext());
            check.setButtonTintList(android.content.res.ColorStateList.valueOf(ui.accent));
            check.setEnabled(session.isConnected());
            check.setChecked(selected.contains(session.key()));
            check.setOnCheckedChangeListener((button, checked) -> {
                if (checked) {
                    selected.add(session.key());
                } else {
                    selected.remove(session.key());
                }
                updateGroupButton();
            });
            card.addView(check);
            LinearLayout info = ui.vertical();
            info.setPadding(ui.dp(4), 0, 0, 0);
            info.addView(ui.label(session.displayName(), 15, ui.text, true));
            info.addView(ui.label(session.address + ":" + session.port, 11, ui.dim, false),
                    topMargin(1));
            TextView state = ui.label(session.status, 11, statusColor(session), false);
            info.addView(state, topMargin(1));
            card.addView(info, new LinearLayout.LayoutParams(0,
                    LinearLayout.LayoutParams.WRAP_CONTENT, 1));
            card.setOnClickListener(view -> listener.onOpenDevice(session));
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            params.topMargin = ui.dp(7);
            listBox.addView(card, params);
        }
        updateGroupButton();
    }

    private int statusColor(DeviceSession session) {
        if (session.isConnected()) {
            return ui.success;
        }
        if (session.connecting) {
            return ui.accent;
        }
        if (!session.lastError.isEmpty() || session.status.contains("失效")
                || session.status.contains("拒绝") || session.status.contains("超时")
                || session.status.contains("失败") || session.status.contains("无法")) {
            return ui.danger;
        }
        return ui.dim;
    }

    private void updateGroupButton() {
        List<DeviceSession> targets = selectedSessions();
        groupButton.setText("发送教师通知（已选 " + targets.size() + " 台）");
        boolean active = !targets.isEmpty();
        groupButton.setEnabled(active);
        groupButton.setTextColor(active ? ui.accentText : ui.dim);
        groupButton.setBackground(active ? ui.round(ui.accent, 8)
                : ui.roundStroke(ui.panel, 8, ui.border, 1));
    }

    public List<DeviceSession> selectedSessions() {
        List<DeviceSession> rows = new ArrayList<>();
        for (DeviceSession session : sessions) {
            if (session.isConnected() && selected.contains(session.key())) {
                rows.add(session);
            }
        }
        return rows;
    }
}
