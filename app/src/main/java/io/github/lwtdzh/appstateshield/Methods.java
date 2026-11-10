package io.github.lwtdzh.appstateshield;

/** Stable IDs: store only exclusions, so every new method inherits enabled. */
public enum Methods {
    SCREENSHOT("screenshot", "截图状态", "Screenshot", "屏蔽截图回调、图片读取及相关信号", "Hide capture callbacks, screenshot reads and signals"),
    VPN("vpn", "VPN 状态", "VPN", "屏蔽 VPN 标识与隧道接口，保留网络连接", "Hide VPN flags and tunnel interfaces; keep connections"),
    PROXY("proxy", "网络代理", "Network proxy", "屏蔽代理信息，保留实际代理请求", "Hide proxy metadata; keep proxy traffic"),
    DEVELOPER("developer", "开发者选项", "Developer options", "返回开发者选项未开启", "Report developer options as off"),
    DEBUG("debug", "USB / 无线调试", "USB / wireless debugging", "屏蔽调试设置、adbd 与 USB 调试属性", "Hide debugging settings, adbd and USB debug properties");

    public final String id, zh, en, detailZh, detailEn;
    Methods(String id, String zh, String en, String detailZh, String detailEn) {
        this.id = id; this.zh = zh; this.en = en; this.detailZh = detailZh; this.detailEn = detailEn;
    }
}
