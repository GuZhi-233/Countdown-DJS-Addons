package com.miaoruixuan.zxremote;

import android.app.Dialog;
import android.content.Context;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;

public final class GroupNotifyDialog {
    public interface Callback {
        void onSend(String title, String body, int duration);
    }

    private GroupNotifyDialog() {
    }

    public static void show(Context context, Ui ui, List<DeviceSession> targets,
                            Callback callback) {
        LinearLayout form = ui.vertical();
        StringBuilder names = new StringBuilder();
        for (DeviceSession session : targets) {
            if (names.length() > 0) {
                names.append("、");
            }
            names.append(session.displayName());
        }
        form.addView(ui.label("发送到 " + targets.size() + " 台设备：" + names,
                11, ui.dim, false));
        EditText title = ui.input("通知标题，例如：下午第三节课调整", false);
        EditText body = ui.input("通知内容", true);
        body.setMinHeight(ui.dp(110));
        form.addView(ui.label("标题", 11, ui.dim, false), topMargin(ui, 8));
        form.addView(title);
        form.addView(ui.label("内容", 11, ui.dim, false), topMargin(ui, 8));
        form.addView(body);
        LinearLayout durationRow = ui.horizontal();
        durationRow.addView(ui.label("显示时长", 11, ui.dim, false));
        SeekBar bar = new SeekBar(context);
        bar.setMax(27);
        bar.setProgress(5);
        LinearLayout.LayoutParams barParams = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        barParams.leftMargin = ui.dp(8);
        durationRow.addView(bar, barParams);
        TextView durationLabel = ui.label("8 秒", 12, ui.text, false);
        durationLabel.setMinimumWidth(ui.dp(48));
        durationRow.addView(durationLabel);
        bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
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
        form.addView(durationRow, topMargin(ui, 6));
        final Dialog[] holder = new Dialog[1];
        holder[0] = ui.dialog("发送教师通知", form, "取消", "发送", view -> {
            String titleText = title.getText().toString().trim();
            String bodyText = body.getText().toString().trim();
            if (titleText.isEmpty() && bodyText.isEmpty()) {
                Toast.makeText(context, "请填写标题或内容", Toast.LENGTH_SHORT).show();
                return;
            }
            holder[0].dismiss();
            if (callback != null) {
                callback.onSend(titleText.isEmpty() ? "教师通知" : titleText, bodyText,
                        bar.getProgress() + 3);
            }
        });
    }

    private static LinearLayout.LayoutParams topMargin(Ui ui, int value) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = ui.dp(value);
        return params;
    }
}
