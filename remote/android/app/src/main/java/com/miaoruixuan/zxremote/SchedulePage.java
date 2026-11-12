package com.miaoruixuan.zxremote;

import android.content.Context;
import android.graphics.Typeface;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;

public final class SchedulePage extends LinearLayout {
    public interface Callback {
        void onDirty();

        void onSaveRequested();

        void onRefreshRequested();
    }

    private static final String[] WEEKDAY_NAMES = {"周一", "周二", "周三", "周四", "周五", "周六", "周日"};
    private static final String[] WEEK_LABELS = {"每周", "单周", "双周"};
    private static final String[] WEEK_KEYS = {"all", "odd", "even"};
    private static final int[][] DEFAULT_PERIODS = {
            {450, 490}, {500, 540}, {550, 590}, {610, 650}, {660, 700},
            {840, 880}, {890, 930}, {940, 980}, {990, 1030}, {1140, 1180}
    };

    private final Ui ui;
    private final Callback callback;
    private JSONObject state = new JSONObject();
    private String rev = "";
    private boolean dirty = false;
    private boolean enabled = true;
    private boolean updatingPlan = false;
    private int day = 1;
    private Spinner planSpinner;
    private LinearLayout listContainer;
    private TextView statusLabel;
    private Button saveButton;
    private Button refreshButton;
    private final Button[] dayButtons = new Button[7];

    public SchedulePage(Context context, Ui ui, Callback callback) {
        super(context);
        this.ui = ui;
        this.callback = callback;
        setOrientation(VERTICAL);
        setBackgroundColor(ui.bg);
        setPadding(ui.dp(12), ui.dp(10), ui.dp(12), ui.dp(6));
        build();
    }

    private void build() {
        LinearLayout planRow = ui.horizontal();
        planRow.addView(ui.label("方案", 12, ui.dim, false));
        planSpinner = ui.spinner(new ArrayList<String>());
        LinearLayout.LayoutParams planParams = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        planParams.leftMargin = ui.dp(8);
        planRow.addView(planSpinner, planParams);
        Button newPlan = ui.smallButton("新建");
        newPlan.setOnClickListener(view -> createPlan());
        planRow.addView(newPlan, marginLeft(8));
        Button renamePlan = ui.smallButton("改名");
        renamePlan.setOnClickListener(view -> renamePlan());
        planRow.addView(renamePlan, marginLeft(6));
        Button deletePlan = ui.smallButton("删除");
        deletePlan.setOnClickListener(view -> deletePlan());
        planRow.addView(deletePlan, marginLeft(6));
        addView(planRow);

        HorizontalScrollView dayScroll = new HorizontalScrollView(getContext());
        dayScroll.setHorizontalScrollBarEnabled(false);
        LinearLayout dayBar = ui.horizontal();
        for (int index = 0; index < WEEKDAY_NAMES.length; index++) {
            final int value = index + 1;
            Button button = new Button(getContext());
            button.setAllCaps(false);
            button.setText(WEEKDAY_NAMES[index]);
            button.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
            button.setMinWidth(0);
            button.setMinimumWidth(0);
            button.setMinHeight(0);
            button.setMinimumHeight(0);
            button.setPadding(ui.dp(10), ui.dp(6), ui.dp(10), ui.dp(6));
            button.setOnClickListener(view -> {
                day = value;
                rebuild();
            });
            dayButtons[index] = button;
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            params.rightMargin = ui.dp(5);
            dayBar.addView(button, params);
        }
        dayScroll.addView(dayBar);
        LinearLayout.LayoutParams dayParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        dayParams.topMargin = ui.dp(8);
        addView(dayScroll, dayParams);

        ScrollView listScroll = new ScrollView(getContext());
        listScroll.setFillViewport(true);
        listContainer = ui.vertical();
        listContainer.setPadding(0, ui.dp(8), 0, ui.dp(8));
        listScroll.addView(listContainer, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));
        addView(listScroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));

        LinearLayout statusRow = ui.horizontal();
        Button periods = ui.smallButton("节次设置");
        periods.setOnClickListener(view -> editPeriods());
        statusRow.addView(periods);
        Button semester = ui.smallButton("学期与周次");
        semester.setOnClickListener(view -> editSemester());
        statusRow.addView(semester, marginLeft(6));
        statusLabel = ui.label("", 11, ui.dim, false);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        statusParams.leftMargin = ui.dp(8);
        statusRow.addView(statusLabel, statusParams);
        refreshButton = ui.smallButton("刷新");
        refreshButton.setOnClickListener(view -> {
            if (callback != null) {
                callback.onRefreshRequested();
            }
        });
        statusRow.addView(refreshButton);
        saveButton = ui.smallButton("保存");
        saveButton.setOnClickListener(view -> {
            if (callback != null) {
                callback.onSaveRequested();
            }
        });
        statusRow.addView(saveButton, marginLeft(6));
        addView(statusRow);

        planSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                if (updatingPlan) {
                    return;
                }
                String name = String.valueOf(parent.getItemAtPosition(position));
                if (!name.equals(state.optString("active", ""))) {
                    put(state, "active", name);
                    markDirty();
                    rebuild();
                }
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });
    }

    private LinearLayout.LayoutParams marginLeft(int value) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.leftMargin = ui.dp(value);
        return params;
    }

    public void setState(JSONObject source, String revision) {
        try {
            state = source == null ? new JSONObject() : new JSONObject(source.toString());
        } catch (Exception exc) {
            state = new JSONObject();
        }
        rev = revision == null ? "" : revision;
        dirty = false;
        ensureStructure();
        updatePlanSpinner();
        rebuild();
        updateStatus();
    }

    public JSONObject state() {
        return state;
    }

    public String rev() {
        return rev;
    }

    public boolean isDirty() {
        return dirty;
    }

    public void markSaved(String revision) {
        rev = revision == null ? "" : revision;
        dirty = false;
        updateStatus();
    }

    public void setEnabled(boolean value) {
        enabled = value;
        saveButton.setEnabled(value);
        refreshButton.setEnabled(value);
    }

    public void showRemoteChanged() {
        statusLabel.setText("电脑端课表已更新，保存前请先刷新");
    }

    public void showStatus(String text) {
        statusLabel.setText(text == null ? "" : text);
        statusLabel.setTextColor(ui.dim);
    }

    public void discardDirty() {
        dirty = false;
        updateStatus();
    }

    private void ensureStructure() {
        JSONObject plans = state.optJSONObject("plans");
        if (plans == null) {
            plans = new JSONObject();
            put(state, "plans", plans);
        }
        if (plans.length() == 0) {
            put(plans, "我的课表", new JSONArray());
        }
        String active = state.optString("active", "");
        if (active.isEmpty() || plans.optJSONArray(active) == null) {
            Iterator<String> keys = plans.keys();
            if (keys.hasNext()) {
                put(state, "active", keys.next());
            }
        }
        JSONArray periods = state.optJSONArray("periods");
        if (periods == null || periods.length() == 0) {
            JSONArray fresh = new JSONArray();
            for (int[] item : DEFAULT_PERIODS) {
                JSONArray pair = new JSONArray();
                add(pair, item[0]);
                add(pair, item[1]);
                add(fresh, pair);
            }
            put(state, "periods", fresh);
        }
    }

    private void updatePlanSpinner() {
        updatingPlan = true;
        JSONObject plans = state.optJSONObject("plans");
        List<String> names = new ArrayList<>();
        if (plans != null) {
            Iterator<String> keys = plans.keys();
            while (keys.hasNext()) {
                names.add(keys.next());
            }
        }
        Collections.sort(names);
        ArrayAdapter<String> adapter = (ArrayAdapter<String>) planSpinner.getAdapter();
        adapter.clear();
        adapter.addAll(names);
        adapter.notifyDataSetChanged();
        String active = state.optString("active", "");
        int index = names.indexOf(active);
        if (index >= 0) {
            planSpinner.setSelection(index);
        }
        updatingPlan = false;
    }

    private JSONArray planArray() {
        JSONObject plans = state.optJSONObject("plans");
        if (plans == null) {
            plans = new JSONObject();
            put(state, "plans", plans);
        }
        String active = state.optString("active", "");
        JSONArray array = plans.optJSONArray(active);
        if (array == null) {
            array = new JSONArray();
            put(plans, active, array);
        }
        return array;
    }

    private List<int[]> periods() {
        List<int[]> rows = new ArrayList<>();
        JSONArray array = state.optJSONArray("periods");
        if (array != null) {
            for (int index = 0; index < array.length(); index++) {
                JSONArray pair = array.optJSONArray(index);
                if (pair == null || pair.length() < 2) {
                    continue;
                }
                rows.add(new int[]{pair.optInt(0, 450), pair.optInt(1, 490)});
            }
        }
        if (rows.isEmpty()) {
            for (int[] item : DEFAULT_PERIODS) {
                rows.add(item);
            }
        }
        return rows;
    }

    private void rebuild() {
        for (int index = 0; index < dayButtons.length; index++) {
            Button button = dayButtons[index];
            if (button == null) {
                continue;
            }
            boolean selected = (index + 1) == day;
            button.setTextColor(selected ? ui.accentText : ui.text);
            button.setBackground(selected ? ui.round(ui.accent, 7)
                    : ui.roundStroke(ui.panel, 7, ui.border, 1));
        }
        listContainer.removeAllViews();
        List<int[]> periods = periods();
        JSONArray entries = planArray();
        for (int period = 0; period < periods.size(); period++) {
            int[] range = periods.get(period);
            List<EntryRef> refs = new ArrayList<>();
            for (int index = 0; index < entries.length(); index++) {
                JSONObject entry = entries.optJSONObject(index);
                if (entry == null) {
                    continue;
                }
                if (entry.optInt("day", 0) == day && entry.optInt("period", -1) == period) {
                    refs.add(new EntryRef(index, entry));
                }
            }
            listContainer.addView(buildPeriodRow(period, range, refs));
        }
    }

    private View buildPeriodRow(int period, int[] range, List<EntryRef> refs) {
        LinearLayout row = ui.horizontal();
        row.setPadding(0, 0, 0, ui.dp(7));
        LinearLayout timeBox = ui.vertical();
        timeBox.setGravity(Gravity.CENTER_HORIZONTAL);
        timeBox.setMinimumWidth(ui.dp(62));
        timeBox.addView(ui.label("第 " + (period + 1) + " 节", 11, ui.dim, true));
        timeBox.addView(ui.label(clock(range[0]), 12, ui.text, false));
        timeBox.addView(ui.label(clock(range[1]), 11, ui.dim, false));
        row.addView(timeBox);
        LinearLayout content = ui.vertical();
        content.setPadding(ui.dp(11), ui.dp(9), ui.dp(11), ui.dp(9));
        if (refs.isEmpty()) {
            content.setBackground(ui.roundStroke(ui.panel, 9, ui.border, 1));
            TextView empty = ui.label("＋ 添加", 13, ui.dim, false);
            empty.setGravity(Gravity.CENTER_VERTICAL);
            content.addView(empty);
        } else {
            content.setBackground(ui.roundStroke(ui.input, 9, ui.border, 1));
            List<String> names = new ArrayList<>();
            List<String> rooms = new ArrayList<>();
            for (EntryRef ref : refs) {
                names.add(str(ref.entry.optString("name", "未命名")));
                String room = str(ref.entry.optString("room", ""));
                if (!room.isEmpty() && !rooms.contains(room)) {
                    rooms.add(room);
                }
            }
            TextView name = ui.label(join(names, "、"), 14, ui.text, true);
            content.addView(name);
            List<String> details = new ArrayList<>();
            if (!rooms.isEmpty()) {
                details.add(join(rooms, "、"));
            }
            String weeks = WEEK_LABELS[Math.max(0, indexOf(WEEK_KEYS,
                    refs.get(0).entry.optString("weeks", "all")))];
            details.add(weeks);
            if (string(refs.get(0).entry.optString("kind", "lesson")).equals("activity")) {
                JSONObject entry = refs.get(0).entry;
                details.add(clock(entry.optInt("start", range[0])) + "-" +
                        clock(entry.optInt("end", range[1])));
            }
            if (refs.size() > 1) {
                details.add("共 " + refs.size() + " 项");
            }
            content.addView(ui.label(join(details, " · "), 11, ui.dim, false));
        }
        final int dayValue = day;
        final int periodValue = period;
        content.setOnClickListener(view -> openCell(dayValue, periodValue));
        LinearLayout.LayoutParams contentParams = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        contentParams.leftMargin = ui.dp(8);
        row.addView(content, contentParams);
        return row;
    }

    private void openCell(int dayValue, int periodValue) {
        List<EntryRef> refs = new ArrayList<>();
        JSONArray entries = planArray();
        for (int index = 0; index < entries.length(); index++) {
            JSONObject entry = entries.optJSONObject(index);
            if (entry != null && entry.optInt("day", 0) == dayValue
                    && entry.optInt("period", -1) == periodValue) {
                refs.add(new EntryRef(index, entry));
            }
        }
        LinearLayout panel = ui.vertical();
        panel.addView(ui.label(WEEKDAY_NAMES[Math.max(0, Math.min(6, dayValue - 1))] +
                " · 第 " + (periodValue + 1) + " 节", 14, ui.text, true));
        final android.app.Dialog[] holder = new android.app.Dialog[1];
        if (refs.isEmpty()) {
            TextView empty = ui.label("这个格子还没有内容", 12, ui.dim, false);
            empty.setPadding(0, ui.dp(8), 0, ui.dp(8));
            panel.addView(empty);
        }
        for (EntryRef ref : refs) {
            Button item = ui.button(describe(ref.entry), false);
            item.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
            item.setOnClickListener(view -> {
                holder[0].dismiss();
                editEntry(dayValue, periodValue, ref.index, ref.entry, false,
                        string(ref.entry.optString("kind", "lesson")).equals("activity"));
            });
            item.setOnLongClickListener(view -> {
                confirmDelete(ref.index, ref.entry);
                return true;
            });
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            params.topMargin = ui.dp(6);
            panel.addView(item, params);
        }
        LinearLayout actions = ui.horizontal();
        Button addLesson = ui.button("新增课程", true);
        addLesson.setOnClickListener(view -> {
            holder[0].dismiss();
            editEntry(dayValue, periodValue, -1, null, true, false);
        });
        actions.addView(addLesson);
        Button addActivity = ui.button("新增活动", false);
        addActivity.setOnClickListener(view -> {
            holder[0].dismiss();
            editEntry(dayValue, periodValue, -1, null, true, true);
        });
        actions.addView(addActivity, marginLeft(8));
        LinearLayout.LayoutParams actionParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        actionParams.topMargin = ui.dp(12);
        panel.addView(actions, actionParams);
        holder[0] = ui.dialog("编辑格子", panel, "关闭", "", null);
    }

    private void editEntry(int dayValue, int periodValue, int index, JSONObject entry,
                           boolean isNew, boolean activityDefault) {
        LinearLayout form = ui.vertical();
        EditText nameEdit = ui.input("课程名称", false);
        EditText roomEdit = ui.input("教室（可选）", false);
        Spinner weeksSpinner = ui.spinner(new ArrayList<>(java.util.Arrays.asList(WEEK_LABELS)));
        Spinner kindSpinner = ui.spinner(new ArrayList<>(java.util.Arrays.asList("课程", "活动")));
        LinearLayout timeRow = ui.horizontal();
        EditText startEdit = ui.input("08:30", false);
        EditText endEdit = ui.input("08:50", false);
        startEdit.setInputType(InputType.TYPE_CLASS_DATETIME);
        endEdit.setInputType(InputType.TYPE_CLASS_DATETIME);
        LinearLayout.LayoutParams half = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        timeRow.addView(startEdit, half);
        TextView dash = ui.label("—", 13, ui.dim, false);
        dash.setPadding(ui.dp(6), 0, ui.dp(6), 0);
        timeRow.addView(dash);
        LinearLayout.LayoutParams half2 = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        timeRow.addView(endEdit, half2);
        form.addView(ui.label("名称", 11, ui.dim, false));
        form.addView(nameEdit);
        form.addView(ui.label("教室", 11, ui.dim, false));
        form.addView(roomEdit);
        form.addView(ui.label("周次", 11, ui.dim, false));
        form.addView(weeksSpinner);
        form.addView(ui.label("类型", 11, ui.dim, false));
        form.addView(kindSpinner);
        form.addView(ui.label("时间（活动填写）", 11, ui.dim, false));
        form.addView(timeRow);
        boolean activity = activityDefault;
        if (entry != null) {
            nameEdit.setText(string(entry.optString("name", "")));
            roomEdit.setText(string(entry.optString("room", "")));
            weeksSpinner.setSelection(Math.max(0, indexOf(WEEK_KEYS,
                    entry.optString("weeks", "all"))));
            activity = string(entry.optString("kind", "lesson")).equals("activity");
            kindSpinner.setSelection(activity ? 1 : 0);
            if (activity) {
                startEdit.setText(clock(entry.optInt("start", 450)));
                endEdit.setText(clock(entry.optInt("end", 490)));
            }
        }
        if (!activity) {
            List<int[]> ranges = periods();
            int start = 450;
            int end = 490;
            if (periodValue >= 0 && periodValue < ranges.size()) {
                start = ranges.get(periodValue)[0];
                end = ranges.get(periodValue)[1];
            }
            startEdit.setText(clock(start));
            endEdit.setText(clock(end));
        }
        timeRow.setVisibility(activity ? View.VISIBLE : View.GONE);
        final boolean[] activityFlag = {activity};
        kindSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                activityFlag[0] = position == 1;
                timeRow.setVisibility(activityFlag[0] ? View.VISIBLE : View.GONE);
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });
        final android.app.Dialog[] holder = new android.app.Dialog[1];
        holder[0] = ui.dialog(isNew ? "新增内容" : "编辑内容", form, "取消", "保存", view -> {
            String name = nameEdit.getText().toString().trim();
            if (name.isEmpty()) {
                Toast.makeText(getContext(), "请输入名称", Toast.LENGTH_SHORT).show();
                return;
            }
            boolean isActivity = kindSpinner.getSelectedItemPosition() == 1;
            int start = parseClock(startEdit.getText().toString());
            int end = parseClock(endEdit.getText().toString());
            if (isActivity && (start < 0 || end < 0 || start >= end)) {
                Toast.makeText(getContext(), "活动时间格式应为 HH:mm，且结束晚于开始",
                        Toast.LENGTH_SHORT).show();
                return;
            }
            JSONObject created = new JSONObject();
            put(created, "day", dayValue);
            put(created, "period", periodValue);
            put(created, "name", name);
            put(created, "room", roomEdit.getText().toString().trim());
            put(created, "weeks", WEEK_KEYS[Math.max(0, weeksSpinner.getSelectedItemPosition())]);
            put(created, "kind", isActivity ? "activity" : "lesson");
            if (isActivity) {
                put(created, "start", start);
                put(created, "end", end);
            } else if (entry != null && entry.has("start") && entry.has("end")) {
                put(created, "start", entry.optInt("start"));
                put(created, "end", entry.optInt("end"));
            }
            JSONArray array = planArray();
            if (isNew) {
                add(array, created);
            } else {
                add(array, index, created);
            }
            markDirty();
            rebuild();
            holder[0].dismiss();
        });
    }

    private void confirmDelete(int index, JSONObject entry) {
        LinearLayout panel = ui.vertical();
        panel.addView(ui.label("删除「" + string(entry.optString("name", "未命名")) + "」？",
                13, ui.text, false));
        final android.app.Dialog[] holder = new android.app.Dialog[1];
        holder[0] = ui.dialog("删除", panel, "取消", "删除", view -> {
            JSONArray old = planArray();
            JSONArray fresh = new JSONArray();
            for (int position = 0; position < old.length(); position++) {
                if (position != index) {
                    add(fresh, old.opt(position));
                }
            }
            JSONObject plans = state.optJSONObject("plans");
            if (plans != null) {
                put(plans, state.optString("active", ""), fresh);
            }
            markDirty();
            rebuild();
            holder[0].dismiss();
        });
    }

    private String describe(JSONObject entry) {
        String kind = string(entry.optString("kind", "lesson")).equals("activity") ? "活动" : "课程";
        String room = string(entry.optString("room", ""));
        String weeks = WEEK_LABELS[Math.max(0, indexOf(WEEK_KEYS,
                entry.optString("weeks", "all")))];
        StringBuilder builder = new StringBuilder();
        builder.append(kind).append(" · ").append(string(entry.optString("name", "未命名")));
        if (!room.isEmpty()) {
            builder.append(" · ").append(room);
        }
        builder.append(" · ").append(weeks);
        if (kind.equals("活动")) {
            builder.append(" · ").append(clock(entry.optInt("start", 0)))
                    .append("-").append(clock(entry.optInt("end", 0)));
        }
        return builder.toString();
    }

    private void createPlan() {
        LinearLayout panel = ui.vertical();
        EditText edit = ui.input("方案名称", false);
        panel.addView(edit);
        final android.app.Dialog[] holder = new android.app.Dialog[1];
        holder[0] = ui.dialog("新建方案", panel, "取消", "创建", view -> {
            String name = edit.getText().toString().trim();
            if (name.isEmpty()) {
                return;
            }
            JSONObject plans = state.optJSONObject("plans");
            if (plans == null) {
                plans = new JSONObject();
                put(state, "plans", plans);
            }
            if (plans.has(name)) {
                Toast.makeText(getContext(), "该方案已存在", Toast.LENGTH_SHORT).show();
                return;
            }
            put(plans, name, new JSONArray());
            put(state, "active", name);
            markDirty();
            updatePlanSpinner();
            rebuild();
            holder[0].dismiss();
        });
    }

    private void renamePlan() {
        JSONObject plans = state.optJSONObject("plans");
        String active = state.optString("active", "");
        if (plans == null || active.isEmpty()) {
            return;
        }
        LinearLayout panel = ui.vertical();
        EditText edit = ui.input("方案名称", false);
        edit.setText(active);
        panel.addView(edit);
        final android.app.Dialog[] holder = new android.app.Dialog[1];
        holder[0] = ui.dialog("重命名方案", panel, "取消", "保存", view -> {
            String name = edit.getText().toString().trim();
            if (name.isEmpty() || name.equals(active)) {
                holder[0].dismiss();
                return;
            }
            if (plans.has(name)) {
                Toast.makeText(getContext(), "该方案已存在", Toast.LENGTH_SHORT).show();
                return;
            }
            JSONObject fresh = new JSONObject();
            Iterator<String> keys = plans.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                try {
                    fresh.put(key.equals(active) ? name : key, plans.get(key));
                } catch (Exception ignored) {
                }
            }
            put(state, "plans", fresh);
            put(state, "active", name);
            markDirty();
            updatePlanSpinner();
            rebuild();
            holder[0].dismiss();
        });
    }

    private void deletePlan() {
        JSONObject plans = state.optJSONObject("plans");
        String active = state.optString("active", "");
        if (plans == null || active.isEmpty()) {
            return;
        }
        if (plans.length() <= 1) {
            Toast.makeText(getContext(), "至少保留一个方案", Toast.LENGTH_SHORT).show();
            return;
        }
        LinearLayout panel = ui.vertical();
        panel.addView(ui.label("删除方案「" + active + "」？", 13, ui.text, false));
        final android.app.Dialog[] holder = new android.app.Dialog[1];
        holder[0] = ui.dialog("删除方案", panel, "取消", "删除", view -> {
            plans.remove(active);
            Iterator<String> keys = plans.keys();
            String next = keys.hasNext() ? keys.next() : "";
            put(state, "active", next);
            markDirty();
            updatePlanSpinner();
            rebuild();
            holder[0].dismiss();
        });
    }

    private void editPeriods() {
        LinearLayout panel = ui.vertical();
        LinearLayout rows = ui.vertical();
        List<PeriodRow> rowList = new ArrayList<>();
        panel.addView(rows);
        Button add = ui.button("新增一节", false);
        LinearLayout.LayoutParams addParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        addParams.topMargin = ui.dp(8);
        panel.addView(add, addParams);
        List<int[]> current = periods();
        for (int[] range : current) {
            addPeriodRow(rows, rowList, range[0], range[1]);
        }
        add.setOnClickListener(view -> {
            int start = 450;
            int end = 490;
            if (!rowList.isEmpty()) {
                PeriodRow last = rowList.get(rowList.size() - 1);
                int value = parseClock(last.end.getText().toString());
                if (value >= 0) {
                    start = Math.min(1430, value + 10);
                    end = Math.min(1439, start + 40);
                }
            }
            if (rowList.size() < 24) {
                addPeriodRow(rows, rowList, start, end);
                relabelPeriods(rowList);
            }
        });
        relabelPeriods(rowList);
        final android.app.Dialog[] holder = new android.app.Dialog[1];
        holder[0] = ui.dialog("节次时间", panel, "取消", "保存", view -> {
            JSONArray fresh = new JSONArray();
            for (PeriodRow row : rowList) {
                int start = parseClock(row.start.getText().toString());
                int end = parseClock(row.end.getText().toString());
                if (start < 0 || end < 0 || start >= end) {
                    Toast.makeText(getContext(), "时间格式应为 HH:mm，且结束晚于开始",
                            Toast.LENGTH_SHORT).show();
                    return;
                }
                JSONArray pair = new JSONArray();
                add(pair, start);
                add(pair, end);
                add(fresh, pair);
            }
            if (fresh.length() == 0) {
                Toast.makeText(getContext(), "至少保留一节", Toast.LENGTH_SHORT).show();
                return;
            }
            put(state, "periods", fresh);
            markDirty();
            rebuild();
            holder[0].dismiss();
        });
    }

    private void addPeriodRow(LinearLayout rows, List<PeriodRow> rowList, int start, int end) {
        LinearLayout row = ui.horizontal();
        row.setPadding(0, ui.dp(4), 0, ui.dp(4));
        TextView label = ui.label("第 1 节", 12, ui.dim, false);
        label.setMinimumWidth(ui.dp(52));
        row.addView(label);
        EditText startEdit = ui.input("08:30", false);
        EditText endEdit = ui.input("08:50", false);
        LinearLayout.LayoutParams editParams = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        row.addView(startEdit, editParams);
        TextView dash = ui.label("—", 13, ui.dim, false);
        dash.setPadding(ui.dp(5), 0, ui.dp(5), 0);
        row.addView(dash);
        LinearLayout.LayoutParams editParams2 = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        row.addView(endEdit, editParams2);
        Button remove = ui.smallButton("×");
        remove.setOnClickListener(view -> {
            rows.removeView(row);
            rowList.remove(findPeriodRow(rowList, row));
            relabelPeriods(rowList);
        });
        row.addView(remove, marginLeft(6));
        startEdit.setText(clock(start));
        endEdit.setText(clock(end));
        rows.addView(row);
        rowList.add(new PeriodRow(row, label, startEdit, endEdit));
    }

    private PeriodRow findPeriodRow(List<PeriodRow> rows, LinearLayout target) {
        for (PeriodRow row : rows) {
            if (row.row == target) {
                return row;
            }
        }
        return null;
    }

    private void relabelPeriods(List<PeriodRow> rows) {
        for (int index = 0; index < rows.size(); index++) {
            rows.get(index).label.setText("第 " + (index + 1) + " 节");
        }
    }

    private void editSemester() {
        LinearLayout panel = ui.vertical();
        CheckBox check = ui.checkBox("设置学期开始日期");
        EditText date = ui.input("yyyy-MM-dd", false);
        Spinner mode = ui.spinner(new ArrayList<>(java.util.Arrays.asList(
                "按周次自动", "只看单周", "只看双周")));
        String start = string(state.optString("semester_start", ""));
        check.setChecked(!start.isEmpty());
        date.setText(start.isEmpty() ? new SimpleDateFormat("yyyy-MM-dd", Locale.CHINA)
                .format(new java.util.Date()) : start);
        date.setEnabled(!start.isEmpty());
        check.setOnCheckedChangeListener((button, checked) -> date.setEnabled(checked));
        String weekMode = state.optString("week_mode", "auto");
        int index = 0;
        if (weekMode.equals("odd")) {
            index = 1;
        } else if (weekMode.equals("even")) {
            index = 2;
        }
        mode.setSelection(index);
        panel.addView(check);
        panel.addView(ui.label("开始日期", 11, ui.dim, false));
        panel.addView(date);
        panel.addView(ui.label("单双周", 11, ui.dim, false));
        panel.addView(mode);
        final android.app.Dialog[] holder = new android.app.Dialog[1];
        holder[0] = ui.dialog("学期与周次", panel, "取消", "保存", view -> {
            String value = date.getText().toString().trim();
            if (check.isChecked()) {
                try {
                    SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd", Locale.CHINA);
                    format.setLenient(false);
                    format.parse(value);
                } catch (Exception exc) {
                    Toast.makeText(getContext(), "日期格式应为 yyyy-MM-dd", Toast.LENGTH_SHORT).show();
                    return;
                }
            }
            put(state, "semester_start", check.isChecked() ? value : "");
            String[] keys = {"auto", "odd", "even"};
            put(state, "week_mode", keys[Math.max(0, mode.getSelectedItemPosition())]);
            markDirty();
            holder[0].dismiss();
        });
    }

    private void markDirty() {
        dirty = true;
        updateStatus();
        if (callback != null) {
            callback.onDirty();
        }
    }

    private void updateStatus() {
        if (dirty) {
            statusLabel.setText("已修改，未保存");
            statusLabel.setTextColor(ui.danger);
        } else if (!rev.isEmpty()) {
            String shortRev = rev.length() > 8 ? rev.substring(0, 8) : rev;
            statusLabel.setText("修订 " + shortRev);
            statusLabel.setTextColor(ui.dim);
        } else {
            statusLabel.setText("");
        }
    }

    private static String clock(int minutes) {
        int value = Math.max(0, minutes);
        return String.format(Locale.CHINA, "%02d:%02d", value / 60 % 24, value % 60);
    }

    private static int parseClock(String text) {
        if (text == null) {
            return -1;
        }
        String value = text.trim();
        if (!value.matches("^\\d{1,2}:\\d{2}$")) {
            return -1;
        }
        String[] parts = value.split(":");
        try {
            int hour = Integer.parseInt(parts[0]);
            int minute = Integer.parseInt(parts[1]);
            if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
                return -1;
            }
            return hour * 60 + minute;
        } catch (Exception exc) {
            return -1;
        }
    }

    private static int indexOf(String[] values, String target) {
        for (int index = 0; index < values.length; index++) {
            if (values[index].equals(target)) {
                return index;
            }
        }
        return 0;
    }

    private static String join(List<String> values, String separator) {
        StringBuilder builder = new StringBuilder();
        for (int index = 0; index < values.size(); index++) {
            if (index > 0) {
                builder.append(separator);
            }
            builder.append(values.get(index));
        }
        return builder.toString();
    }

    private static String string(String value) {
        return value == null ? "" : value;
    }

    private static String str(String value) {
        return value == null ? "" : value;
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

    private static void add(JSONArray array, int index, Object value) {
        try {
            array.put(index, value);
        } catch (Exception ignored) {
        }
    }

    private static final class EntryRef {
        final int index;
        final JSONObject entry;

        EntryRef(int index, JSONObject entry) {
            this.index = index;
            this.entry = entry;
        }
    }

    private static final class PeriodRow {
        final LinearLayout row;
        final TextView label;
        final EditText start;
        final EditText end;

        PeriodRow(LinearLayout row, TextView label, EditText start, EditText end) {
            this.row = row;
            this.label = label;
            this.start = start;
            this.end = end;
        }
    }
}
