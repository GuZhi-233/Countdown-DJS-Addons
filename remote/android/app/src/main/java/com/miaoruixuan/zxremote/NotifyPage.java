package com.miaoruixuan.zxremote;

import android.content.Context;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public final class NotifyPage extends LinearLayout {
    public interface Callback {
        void onSend(String title, String body, int duration);
    }

    private final Ui ui;
    private final Callback callback;
    private EditText titleEdit;
    private EditText bodyEdit;
    private SeekBar durationBar;
    private TextView durationLabel;
    private TextView statusLabel;
    private LinearLayout historyBox;
    private Button sendButton;

    public NotifyPage(Context context, Ui ui, Callback callback) {
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
        card.addView(ui.label("教师通知", 16, ui.text, true));
        card.addView(ui.label("教师通知会强制置顶于所有窗口之上。",
                11, ui.dim, false));
        titleEdit = ui.input("通知标题，例如：下午第三节课调整", false);
        card.addView(titleEdit, topMargin(8));
        bodyEdit = ui.input("通知内容", true);
        bodyEdit.setMinHeight(ui.dp(120));
        card.addView(bodyEdit, topMargin(8));
        LinearLayout durationRow = ui.horizontal();
        durationRow.addView(ui.label("显示时长", 11, ui.dim, false));
        durationBar = new SeekBar(getContext());
        durationBar.setMax(27);
        durationBar.setProgress(5);
        LinearLayout.LayoutParams barParams = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        barParams.leftMargin = ui.dp(8);
        durationRow.addView(durationBar, barParams);
        durationLabel = ui.label("8 秒", 12, ui.text, false);
        durationLabel.setMinimumWidth(ui.dp(48));
        durationRow.addView(durationLabel);
        card.addView(durationRow, topMargin(4));
        durationBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                durationLabel.setText((progress + 3) + " 秒");
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {
            }
        });
        sendButton = ui.button("发送教师通知", true);
        sendButton.setOnClickListener(view -> send());
        LinearLayout.LayoutParams sendParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        sendParams.topMargin = ui.dp(12);
        card.addView(sendButton, sendParams);
        statusLabel = ui.label("", 11, ui.dim, false);
        card.addView(statusLabel, topMargin(8));
        root.addView(card, topMargin(4));

        LinearLayout historyCard = ui.card();
        historyCard.addView(ui.label("最近发送", 16, ui.text, true));
        historyBox = ui.vertical();
        historyCard.addView(historyBox, topMargin(6));
        root.addView(historyCard, topMargin(10));
    }

    private LinearLayout.LayoutParams topMargin(int value) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = ui.dp(value);
        return params;
    }

    private void send() {
        String title = titleEdit.getText().toString().trim();
        String body = bodyEdit.getText().toString().trim();
        if (title.isEmpty() && body.isEmpty()) {
            statusLabel.setText("请填写标题或内容");
            return;
        }
        statusLabel.setText("正在发送…");
        if (callback != null) {
            callback.onSend(title.isEmpty() ? "教师通知" : title, body,
                    durationBar.getProgress() + 3);
        }
    }

    public void onResult(boolean ok, String message) {
        statusLabel.setText(ok ? "教师通知已发送" : (message == null ? "发送失败" : message));
        statusLabel.setTextColor(ok ? ui.success : ui.danger);
    }

    public void setEnabled(boolean enabled) {
        sendButton.setEnabled(enabled);
    }

    public void setHistory(JSONArray rows) {
        historyBox.removeAllViews();
        if (rows == null || rows.length() == 0) {
            historyBox.addView(ui.label("暂无记录", 12, ui.dim, false));
            return;
        }
        SimpleDateFormat format = new SimpleDateFormat("MM-dd HH:mm", Locale.CHINA);
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.optJSONObject(index);
            if (row == null) {
                continue;
            }
            long stamp = row.optLong("ts", 0);
            String title = row.optString("title", "通知");
            String text = (stamp > 0 ? format.format(new Date(stamp * 1000)) : "") +
                    " · 教师通知 · " + title;
            TextView line = ui.label(text, 12, ui.text, false);
            line.setPadding(0, ui.dp(5), 0, ui.dp(5));
            historyBox.addView(line);
        }
    }
}
