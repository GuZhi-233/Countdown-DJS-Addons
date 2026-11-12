package com.miaoruixuan.zxremote;

import android.content.Context;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public final class DevicePage extends LinearLayout {
    public interface Callback {
        void onReconnect(DeviceSession session);

        void onUnpair(DeviceSession session);

        void onRemove(DeviceSession session);

        void onAlias(DeviceSession session, String alias);
    }

    private final Ui ui;
    private final Callback callback;
    private TextView hostLabel;
    private TextView addressLabel;
    private TextView stateLabel;
    private TextView versionLabel;
    private EditText aliasEdit;
    private Button unpairButton;
    private Button removeButton;
    private DeviceSession session;

    public DevicePage(Context context, Ui ui, Callback callback) {
        super(context);
        this.ui = ui;
        this.callback = callback;
        setOrientation(VERTICAL);
        setBackgroundColor(ui.bg);
        setPadding(ui.dp(12), ui.dp(10), ui.dp(12), ui.dp(6));
        build();
    }

    private void build() {
        ScrollView scroll = new ScrollView(getContext());
        scroll.setFillViewport(true);
        LinearLayout root = ui.vertical();
        root.setPadding(0, 0, 0, ui.dp(12));
        scroll.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));
        addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.MATCH_PARENT));

        LinearLayout card = ui.card();
        card.addView(ui.label("设备信息", 16, ui.text, true));
        hostLabel = ui.label("主机：—", 13, ui.text, false);
        addressLabel = ui.label("地址：—", 12, ui.dim, false);
        stateLabel = ui.label("状态：未连接", 12, ui.dim, false);
        versionLabel = ui.label("ZX 版本：—", 12, ui.dim, false);
        card.addView(hostLabel, topMargin(6));
        card.addView(addressLabel, topMargin(4));
        card.addView(stateLabel, topMargin(4));
        card.addView(versionLabel, topMargin(4));
        LinearLayout actions = ui.horizontal();
        Button reconnect = ui.button("重新连接", true);
        reconnect.setOnClickListener(view -> {
            if (session != null) {
                callback.onReconnect(session);
            }
        });
        actions.addView(reconnect);
        unpairButton = ui.button("解除配对", false);
        unpairButton.setTextColor(ui.danger);
        unpairButton.setOnClickListener(view -> {
            if (session != null) {
                callback.onUnpair(session);
            }
        });
        LinearLayout.LayoutParams unpairParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        unpairParams.leftMargin = ui.dp(8);
        actions.addView(unpairButton, unpairParams);
        removeButton = ui.button("移除设备", false);
        removeButton.setTextColor(ui.danger);
        removeButton.setOnClickListener(view -> {
            if (session != null) {
                callback.onRemove(session);
            }
        });
        LinearLayout.LayoutParams removeParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        removeParams.leftMargin = ui.dp(8);
        actions.addView(removeButton, removeParams);
        card.addView(actions, topMargin(10));
        root.addView(card, topMargin(4));

        LinearLayout aliasCard = ui.card();
        aliasCard.addView(ui.label("本机备注", 16, ui.text, true));
        aliasCard.addView(ui.label("只保存在手机上，用于区分多台电脑。", 11, ui.dim, false),
                topMargin(4));
        aliasEdit = ui.input("例如：高一(1)班电脑", false);
        aliasCard.addView(aliasEdit, topMargin(8));
        Button saveAlias = ui.button("保存备注", false);
        saveAlias.setOnClickListener(view -> {
            if (session != null) {
                callback.onAlias(session, aliasEdit.getText().toString());
            }
        });
        LinearLayout.LayoutParams saveParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        saveParams.topMargin = ui.dp(8);
        aliasCard.addView(saveAlias, saveParams);
        root.addView(aliasCard, topMargin(10));

        LinearLayout help = ui.card();
        help.addView(ui.label("说明", 16, ui.text, true));
        help.addView(ui.label("解除配对会通知电脑端移除本机；移除设备只删除手机上的记录。",
                12, ui.dim, false), topMargin(6));
        help.addView(ui.label("连接失败时，请确认电脑端 ZX 已启用远程控制，并检查两台设备是否在同一局域网。",
                12, ui.dim, false), topMargin(4));
        root.addView(help, topMargin(10));
    }

    private LinearLayout.LayoutParams topMargin(int value) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = ui.dp(value);
        return params;
    }

    public void setSession(DeviceSession value) {
        session = value;
        if (session == null) {
            return;
        }
        hostLabel.setText("主机：" + session.displayName());
        addressLabel.setText("地址：" + session.address + ":" + session.port);
        stateLabel.setText("状态：" + session.status);
        stateLabel.setTextColor(session.isConnected() ? ui.success
                : (session.connecting ? ui.accent : ui.danger));
        versionLabel.setText("ZX 版本：" +
                (session.hostVersion.isEmpty() ? "—" : session.hostVersion));
        aliasEdit.setText(session.alias);
        unpairButton.setEnabled(session.isConnected());
        removeButton.setEnabled(true);
    }
}
