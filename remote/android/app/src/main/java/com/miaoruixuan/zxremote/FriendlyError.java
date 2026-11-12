package com.miaoruixuan.zxremote;

import java.util.Locale;

public final class FriendlyError {
    private FriendlyError() {
    }

    public static String translate(String raw) {
        if (raw == null) {
            return "连接失败，请稍后重试";
        }
        String value = raw.trim();
        if (value.isEmpty()) {
            return "连接失败，请稍后重试";
        }
        String lower = value.toLowerCase(Locale.ROOT);
        if (lower.contains("connection refused") || lower.contains("econnrefused")) {
            return "电脑端拒绝连接，请确认 ZX 已启用远程控制";
        }
        if (lower.contains("timed out") || lower.contains("timeout")) {
            return "连接超时，请检查电脑端地址与防火墙";
        }
        if (lower.contains("network is unreachable")) {
            return "网络不可达，请确认手机与电脑在同一局域网";
        }
        if (lower.contains("no route to host")) {
            return "无法路由到电脑，请检查网络连接";
        }
        if (lower.contains("connection reset") || lower.contains("broken pipe")
                || lower.contains("socket closed") || lower.contains("connection closed")) {
            return "连接已被电脑端关闭";
        }
        if (lower.contains("permission denied") || lower.contains("eacces")) {
            return "网络权限被拒绝";
        }
        if (lower.contains("failed to connect") || lower.contains("unable to connect")
                || lower.contains("connectexception") || lower.contains("sockettimeoutexception")) {
            return "无法连接到电脑端";
        }
        if (containsChinese(value)) {
            return value;
        }
        return "连接失败，请稍后重试";
    }

    private static boolean containsChinese(String value) {
        for (int index = 0; index < value.length(); index++) {
            if (value.charAt(index) >= 0x4E00 && value.charAt(index) <= 0x9FFF) {
                return true;
            }
        }
        return false;
    }
}
