package com.miaoruixuan.zxremote;

import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.content.res.ColorStateList;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import java.util.List;

public final class Ui {
    public final boolean dark;
    public final int bg;
    public final int panel;
    public final int panel2;
    public final int input;
    public final int text;
    public final int dim;
    public final int border;
    public final int accent;
    public final int accentText;
    public final int danger;
    public final int success;
    public final int blue;
    private final Context context;

    public Ui(Context context, boolean dark) {
        this.context = context;
        this.dark = dark;
        if (dark) {
            bg = 0xFF12141C;
            panel = 0xFF1A1D27;
            panel2 = 0xFF232634;
            input = 0xFF232634;
            text = 0xFFECEEF4;
            dim = 0xFF8B90A0;
            border = 0xFF3A3F52;
            accent = 0xFFFBBF24;
            accentText = 0xFF12141C;
            danger = 0xFFF43F5E;
            success = 0xFF34D399;
            blue = 0xFF5AA9FF;
        } else {
            bg = 0xFFF4F5F7;
            panel = 0xFFFFFFFF;
            panel2 = 0xFFEEF0F4;
            input = 0xFFFFFFFF;
            text = 0xFF12141C;
            dim = 0xFF5C6270;
            border = 0xFFD7DAE0;
            accent = 0xFFC2410C;
            accentText = 0xFFFFFFFF;
            danger = 0xFFBE123C;
            success = 0xFF059669;
            blue = 0xFF1F6FD0;
        }
    }

    public static boolean systemDark(Context context) {
        int mode = context.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        return mode == Configuration.UI_MODE_NIGHT_YES;
    }

    public int dp(float value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    public GradientDrawable round(int color, float radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        return drawable;
    }

    public GradientDrawable roundStroke(int fill, float radius, int stroke, float width) {
        GradientDrawable drawable = round(fill, radius);
        drawable.setStroke(Math.max(1, dp(width)), stroke);
        return drawable;
    }

    public TextView label(String value, float size, int color, boolean bold) {
        TextView view = new TextView(context);
        view.setText(value == null ? "" : value);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
        view.setTextColor(color);
        if (bold) {
            view.setTypeface(Typeface.DEFAULT_BOLD);
        }
        view.setLineSpacing(dp(2), 1.0f);
        return view;
    }

    public TextView title(String value) {
        TextView view = label(value, 24, text, true);
        view.setPadding(0, 0, 0, dp(2));
        return view;
    }

    public TextView dim(String value) {
        return label(value, 12, dim, false);
    }

    public Button button(String value, boolean primary) {
        Button view = new Button(context);
        view.setAllCaps(false);
        view.setText(value);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        view.setTextColor(primary ? accentText : text);
        view.setTypeface(primary ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
        view.setBackground(primary ? round(accent, 8) : roundStroke(panel, 8, border, 1));
        view.setPadding(dp(14), dp(9), dp(14), dp(9));
        view.setMinHeight(0);
        view.setMinimumHeight(0);
        view.setMinWidth(0);
        view.setMinimumWidth(0);
        if (Build.VERSION.SDK_INT >= 21) {
            view.setElevation(0);
        }
        return view;
    }

    public Button smallButton(String value) {
        Button view = button(value, false);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        view.setPadding(dp(9), dp(6), dp(9), dp(6));
        return view;
    }

    public EditText input(String hint, boolean multiline) {
        EditText view = new EditText(context);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        view.setTextColor(text);
        view.setHintTextColor(dim);
        view.setHint(hint == null ? "" : hint);
        view.setBackground(roundStroke(input, 7, border, 1));
        view.setPadding(dp(11), dp(9), dp(11), dp(9));
        view.setSingleLine(!multiline);
        if (multiline) {
            view.setGravity(Gravity.TOP | Gravity.START);
            view.setMinLines(4);
            view.setInputType(android.text.InputType.TYPE_CLASS_TEXT |
                    android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        }
        return view;
    }

    public CheckBox checkBox(String value) {
        CheckBox view = new CheckBox(context);
        view.setText(value);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        view.setTextColor(text);
        if (Build.VERSION.SDK_INT >= 21) {
            view.setButtonTintList(ColorStateList.valueOf(accent));
        }
        return view;
    }

    public Spinner spinner(List<String> items) {
        Spinner view = new Spinner(context);
        view.setBackground(roundStroke(input, 7, border, 1));
        view.setPadding(dp(6), 0, dp(6), 0);
        ArrayAdapter<String> adapter = new ArrayAdapter<String>(context,
                android.R.layout.simple_spinner_item, items) {
            @Override
            public View getView(int position, View convertView, ViewGroup parent) {
                TextView row = (TextView) super.getView(position, convertView, parent);
                row.setTextColor(text);
                row.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
                row.setPadding(dp(8), dp(8), dp(8), dp(8));
                return row;
            }

            @Override
            public View getDropDownView(int position, View convertView, ViewGroup parent) {
                TextView row = (TextView) super.getDropDownView(position, convertView, parent);
                row.setTextColor(text);
                row.setBackgroundColor(panel);
                row.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
                row.setPadding(dp(12), dp(11), dp(12), dp(11));
                return row;
            }
        };
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        view.setAdapter(adapter);
        return view;
    }

    public LinearLayout vertical() {
        LinearLayout layout = new LinearLayout(context);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    public LinearLayout horizontal() {
        LinearLayout layout = new LinearLayout(context);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        layout.setGravity(Gravity.CENTER_VERTICAL);
        return layout;
    }

    public LinearLayout card() {
        LinearLayout layout = vertical();
        layout.setBackground(roundStroke(panel, 12, border, 1));
        layout.setPadding(dp(14), dp(13), dp(14), dp(13));
        return layout;
    }

    public View gap(int height) {
        View view = new View(context);
        view.setLayoutParams(new LinearLayout.LayoutParams(1, dp(height)));
        return view;
    }

    public void applyWindow(Activity activity) {
        Window window = activity.getWindow();
        window.setStatusBarColor(bg);
        window.setNavigationBarColor(bg);
        int flags = window.getDecorView().getSystemUiVisibility();
        if (dark) {
            flags &= ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= 26) {
                flags &= ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            }
        } else {
            flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= 26) {
                flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            }
        }
        window.getDecorView().setSystemUiVisibility(flags);
    }

    public Dialog dialog(String title, View content, String negativeText,
                         String positiveText, View.OnClickListener positive) {
        Dialog dialog = new Dialog(context);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        LinearLayout box = vertical();
        box.setBackground(roundStroke(panel, 14, border, 1));
        box.setPadding(dp(18), dp(16), dp(18), dp(14));
        if (title != null && !title.isEmpty()) {
            box.addView(label(title, 17, text, true));
        }
        ScrollView scroll = new ScrollView(context);
        scroll.setFillViewport(false);
        FrameLayout holder = new FrameLayout(context);
        holder.addView(content, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT));
        scroll.addView(holder, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT));
        LinearLayout.LayoutParams scrollParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        scrollParams.topMargin = dp(10);
        box.addView(scroll, scrollParams);
        LinearLayout actions = horizontal();
        actions.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams actionsParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        actionsParams.topMargin = dp(12);
        box.addView(actions, actionsParams);
        if (negativeText != null && !negativeText.isEmpty()) {
            Button cancel = button(negativeText, false);
            cancel.setOnClickListener(view -> dialog.dismiss());
            LinearLayout.LayoutParams buttonParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            buttonParams.leftMargin = dp(8);
            actions.addView(cancel, buttonParams);
        }
        if (positiveText != null && !positiveText.isEmpty()) {
            Button confirm = button(positiveText, true);
            if (positive != null) {
                confirm.setOnClickListener(positive);
            } else {
                confirm.setOnClickListener(view -> dialog.dismiss());
            }
            LinearLayout.LayoutParams confirmParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            confirmParams.leftMargin = dp(8);
            actions.addView(confirm, confirmParams);
        }
        dialog.setContentView(box);
        dialog.show();
        Window window = dialog.getWindow();
        if (window != null) {
            window.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            int width = (int) (context.getResources().getDisplayMetrics().widthPixels * 0.92);
            window.setLayout(width, LinearLayout.LayoutParams.WRAP_CONTENT);
        }
        final int screenHeight = context.getResources().getDisplayMetrics().heightPixels;
        scroll.post(() -> {
            if (scroll.getChildCount() == 0) {
                return;
            }
            int desired = scroll.getChildAt(0).getHeight();
            int max = (int) (screenHeight * 0.62);
            ViewGroup.LayoutParams params = scroll.getLayoutParams();
            params.height = Math.min(Math.max(desired, dp(72)), max);
            scroll.setLayoutParams(params);
        });
        return dialog;
    }

    public static void margins(View view, int left, int top, int right, int bottom) {
        ViewGroup.LayoutParams params = view.getLayoutParams();
        if (params instanceof ViewGroup.MarginLayoutParams) {
            ((ViewGroup.MarginLayoutParams) params).setMargins(left, top, right, bottom);
            view.setLayoutParams(params);
        }
    }
}
