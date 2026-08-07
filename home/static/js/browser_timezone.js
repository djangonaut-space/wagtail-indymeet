function getBrowserTimezone() {
    try {
        if (typeof Intl === "undefined" || !Intl.DateTimeFormat) {
            return "";
        }
        return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch {
        return "";
    }
}
