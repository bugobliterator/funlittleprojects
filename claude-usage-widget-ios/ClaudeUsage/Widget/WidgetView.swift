import SwiftUI
import WidgetKit

/// Widget container background. On iOS 26 the user picks the widget appearance from
/// the home screen — Color / Tint / Clear. We adapt:
///   * `.fullColor`  → Apple's "Color" mode → provide a dark branded gradient
///   * `.accented`   → "Tint" mode → keep transparent; system applies its tint
///   * `.vibrant`    → "Clear" mode → keep transparent; wallpaper shows through as glass
struct WidgetBackground: View {
    @Environment(\.widgetRenderingMode) private var renderingMode

    var body: some View {
        switch renderingMode {
        case .fullColor:
            // Translucent dark glass — `.ultraThickMaterial` gives the blurred-glass
            // texture, the black overlay deepens it toward dark mode, and the radial
            // glow tints the upper-right corner. The material is the thickest one,
            // so the wallpaper only barely bleeds through — enough to give a sense
            // of depth without compromising readability of the rings.
            ZStack {
                Rectangle().fill(.ultraThickMaterial)
                Color.black.opacity(0.45)
                RadialGradient(
                    gradient: Gradient(colors: [Color.orangeBrand.opacity(0.50), .clear]),
                    center: .init(x: 0.88, y: 0.10), startRadius: 0, endRadius: 300,
                )
            }
            .environment(\.colorScheme, .dark)
        default:
            // Tint / Clear / unknown → let the system render its own treatment.
            Color.clear
        }
    }
}

/// Brand-accent glow drawn inside the body so it tints whatever sits behind (system
/// glass in Clear/Tint modes, our dark gradient in Color mode).
private struct BrandGlow: View {
    @Environment(\.widgetRenderingMode) private var renderingMode

    var body: some View {
        // Skip in `.fullColor` since WidgetBackground already draws the glow there;
        // doubling it just makes the corner look washed-out.
        if renderingMode != .fullColor {
            RadialGradient(
                gradient: Gradient(colors: [Color.orangeBrand.opacity(0.55), .clear]),
                center: .init(x: 0.88, y: 0.10), startRadius: 0, endRadius: 260,
            )
            .allowsHitTesting(false)
        }
    }
}

struct WidgetView: View {
    @Environment(\.widgetRenderingMode) private var renderingMode
    let entry: UsageEntry

    @ViewBuilder
    var body: some View {
        if renderingMode == .fullColor {
            // In `.fullColor` ("Default" or "Dark" appearance) we paint our own dark
            // gradient as the widget background, so the body text and materials must
            // resolve in dark color scheme — otherwise `.primary` renders as black on
            // dark and `.regularMaterial` renders as a bright panel.
            content.environment(\.colorScheme, .dark)
        } else {
            // Tint/Clear modes: let the system control coloring so the body text
            // adapts to whatever treatment the OS applies.
            content
        }
    }

    @ViewBuilder
    private var content: some View {
        switch entry.state {
        case .unconfigured: StateMessageView(headline: "Claude Usage", message: "Tap to log in")
        case .loading:      StateMessageView(headline: "Claude Usage", message: "Loading…")
        case .authError:    StateMessageView(headline: "Claude Usage", message: "Tap to re-auth")
        case .networkError: StateMessageView(headline: "Claude Usage", message: "Network error · retry")
        case .loaded(let loaded): LoadedWidgetView(loaded: loaded)
        }
    }
}

private struct StateMessageView: View {
    let headline: String
    let message: String
    var body: some View {
        ZStack(alignment: .topTrailing) {
            BrandGlow()
            VStack(alignment: .leading, spacing: 6) {
                HeaderView(fetchedAt: nil, mock: false)
                Spacer()
                Text(message)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(.primary)
                Spacer()
            }
            .padding(14)
        }
    }
}

private struct LoadedWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let loaded: WidgetState.Loaded

    var body: some View {
        ZStack {
            BrandGlow()
            content
        }
    }

    private var content: some View {
        GeometryReader { geo in
            let headerHeight: CGFloat = 24
            let gap: CGFloat = 10
            let bodyW = geo.size.width
            let bodyH = geo.size.height - headerHeight - gap

            VStack(spacing: gap) {
                HeaderView(fetchedAt: loaded.fetchedAt, mock: loaded.mock)
                    .frame(height: headerHeight)

                // systemLarge is square-ish (tall body) → stacked two-row layout with rings
                // on top and a full-width countdown strip on the bottom. systemMedium is
                // wide → three columns: two rings + countdown card.
                if family == .systemLarge {
                    twoRowBody(width: bodyW, height: bodyH, gap: gap)
                } else {
                    threeColBody(width: bodyW, height: bodyH, gap: gap)
                }
            }
        }
        .padding(14)
    }

    @ViewBuilder
    private func twoRowBody(width: CGFloat, height: CGFloat, gap: CGFloat) -> some View {
        let countdownH: CGFloat = 56
        let ringsH = height - countdownH - gap
        let ringW = (width - gap) / 2
        VStack(spacing: gap) {
            HStack(spacing: gap) {
                RingCell(percent: loaded.fiveHourPct,
                         label: "5-hour",
                         sub: subFiveHour(loaded.fiveHourResetsAt),
                         empty: false)
                    .frame(width: ringW, height: ringsH)
                RingCell(percent: loaded.sevenDayPct ?? 0,
                         label: loaded.sevenDayLabel,
                         sub: loaded.sevenDayPct == nil ? "no data" : subSevenDay(loaded.sevenDayResetsAt),
                         empty: loaded.sevenDayPct == nil)
                    .frame(width: ringW, height: ringsH)
            }
            CountdownStrip(resetsAt: loaded.fiveHourResetsAt, barPercent: loaded.fiveHourPct)
                .frame(height: countdownH)
        }
    }

    @ViewBuilder
    private func threeColBody(width: CGFloat, height: CGFloat, gap: CGFloat) -> some View {
        let cellW = (width - 2 * gap) / 3
        HStack(spacing: gap) {
            RingCell(percent: loaded.fiveHourPct,
                     label: "5-hour",
                     sub: subFiveHour(loaded.fiveHourResetsAt),
                     empty: false)
                .frame(width: cellW)
            RingCell(percent: loaded.sevenDayPct ?? 0,
                     label: loaded.sevenDayLabel,
                     sub: loaded.sevenDayPct == nil ? "no data" : subSevenDay(loaded.sevenDayResetsAt),
                     empty: loaded.sevenDayPct == nil)
                .frame(width: cellW)
            CountdownCard(resetsAt: loaded.fiveHourResetsAt, barPercent: loaded.fiveHourPct)
                .frame(width: cellW)
        }
        .frame(height: height)
    }
}

// MARK: - Header

private struct HeaderView: View {
    let fetchedAt: Date?
    let mock: Bool

    var body: some View {
        HStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(
                        LinearGradient(
                            colors: [Color.peachBrand, Color.orangeBrand],
                            startPoint: .topLeading, endPoint: .bottomTrailing,
                        )
                    )
                    .frame(width: 20, height: 20)
                    .shadow(color: Color.orangeBrand.opacity(0.6), radius: 4)
                Text("C")
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(.white)
            }
            Text("Claude Usage")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(.primary)
            Spacer()
            if let fetchedAt {
                Text(rightLabel(fetchedAt: fetchedAt, mock: mock))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func rightLabel(fetchedAt: Date, mock: Bool) -> String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        let time = f.string(from: fetchedAt)
        return mock ? "Opus · \(time) · MOCK" : "Opus · \(time)"
    }
}

// MARK: - Ring cell

private struct RingCell: View {
    let percent: Double
    let label: String
    let sub: String
    let empty: Bool

    var body: some View {
        GeometryReader { geo in
            // Scale the ring with the available cell area but bias up for presence —
            // the previous max of 84pt left a lot of empty space on systemMedium.
            let diameter = min(96, min(geo.size.width - 4, geo.size.height - 38))
            let stroke: CGFloat = max(8, diameter * 0.11)
            VStack(spacing: 0) {
                ZStack {
                    Circle()
                        .stroke(Color.primary.opacity(0.12), lineWidth: stroke)
                        .frame(width: diameter, height: diameter)
                    if !empty {
                        let fraction = max(0, min(percent / 100, 1))
                        Circle()
                            .trim(from: 0, to: fraction)
                            .stroke(
                                AngularGradient(
                                    colors: [Color.orangeBrand, Color.peachBrand, Color.orangeBrand],
                                    center: .center,
                                    startAngle: .degrees(-90),
                                    endAngle: .degrees(270),
                                ),
                                style: StrokeStyle(lineWidth: stroke, lineCap: .round),
                            )
                            .rotationEffect(.degrees(-90))
                            .frame(width: diameter, height: diameter)
                            .shadow(color: Color.orangeBrand.opacity(0.55), radius: 8)
                    }
                    if empty {
                        Text("—")
                            .font(.system(size: diameter * 0.20, weight: .bold))
                            .foregroundStyle(.secondary)
                    } else {
                        Text("\(Int(percent.rounded()))%")
                            .font(.system(size: diameter * 0.26, weight: .bold))
                            .foregroundStyle(.primary)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 2)

                Text(label.uppercased())
                    .font(.system(size: 10, weight: .bold))
                    .tracking(0.6)
                    .foregroundStyle(.secondary)
                    .padding(.top, 6)

                Text(sub)
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
                    .multilineTextAlignment(.center)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                    .padding(.top, 2)
                    .padding(.horizontal, 2)
            }
        }
    }
}

// MARK: - Countdown card / strip (Liquid Glass)

private struct CountdownCard: View {
    let resetsAt: Date?
    let barPercent: Double

    var body: some View {
        VStack(spacing: 2) {
            Text("RESETS IN")
                .font(.system(size: 10, weight: .bold))
                .tracking(0.8)
                .foregroundStyle(.secondary)
                .padding(.top, 14)
            Text(formatCountdown(resetsAt))
                .font(.system(size: 24, weight: .bold))
                .foregroundStyle(Color.peachBrand)
                .minimumScaleFactor(0.6)
                .lineLimit(1)
                .padding(.horizontal, 6)
            Text("5-hour window")
                .font(.system(size: 9))
                .foregroundStyle(.tertiary)
                .padding(.top, 2)
            Spacer(minLength: 0)
            ProgressBar(percent: barPercent)
                .padding(.horizontal, 14)
                .padding(.bottom, 12)
                .frame(height: 3)
        }
        .frame(maxWidth: .infinity)
        .glassPanel(cornerRadius: 16)
    }
}

private struct CountdownStrip: View {
    let resetsAt: Date?
    let barPercent: Double

    var body: some View {
        VStack {
            HStack {
                Text("RESETS IN")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text(formatCountdown(resetsAt))
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(Color.peachBrand)
            }
            .padding(.horizontal, 12)
            .padding(.top, 10)
            Spacer()
            ProgressBar(percent: barPercent)
                .padding(.horizontal, 12)
                .padding(.bottom, 10)
                .frame(height: 4)
        }
        .glassPanel(cornerRadius: 14)
    }
}

private struct ProgressBar: View {
    let percent: Double
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.primary.opacity(0.12))
                if percent > 0 {
                    let fraction = max(0, min(percent / 100, 1))
                    Capsule()
                        .fill(Color.orangeBrand)
                        .frame(width: geo.size.width * fraction)
                }
            }
        }
    }
}

// MARK: - Glass panel modifier

private extension View {
    /// Applies the platform's Liquid Glass effect on iOS 26+, falling back to a thin
    /// material background with a subtle stroke on earlier iOS. Keeping the same shape
    /// on both branches avoids layout jumps when the OS upgrades.
    func glassPanel(cornerRadius: CGFloat) -> some View {
        modifier(GlassPanel(cornerRadius: cornerRadius))
    }
}

private struct GlassPanel: ViewModifier {
    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        // `.glassEffect(_:in:)` replaces content with a glass-shaped placeholder on
        // iOS 26.4 — text inside vanishes. Using `.background(.regularMaterial, in:)`
        // is the safer pattern: on iOS 26 the material is unified with Liquid Glass
        // so the visual is the same wallpaper-aware translucency, and the content
        // (text, progress bars) stays visible on top.
        content
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .strokeBorder(Color.orangeBrand.opacity(0.30), lineWidth: 1)
            )
    }
}

// MARK: - Formatting helpers

private func formatCountdown(_ date: Date?) -> String {
    guard let date else { return "—" }
    let interval = date.timeIntervalSinceNow
    if interval <= 0 { return "now" }
    let minutes = Int(interval / 60)
    let hours = minutes / 60
    let rem = minutes % 60
    if hours <= 0 { return "\(minutes)m" }
    if hours >= 24 { return "\(hours / 24)d \(hours % 24)h" }
    return "\(hours)h \(rem)m"
}

private func subFiveHour(_ date: Date?) -> String {
    guard let date else { return "resets soon" }
    let f = DateFormatter()
    if date.timeIntervalSinceNow < 24 * 60 * 60 {
        f.dateFormat = "HH:mm"
        return "resets \(f.string(from: date))"
    } else {
        f.dateFormat = "EEE d MMM"
        return "resets \(f.string(from: date))"
    }
}

private func subSevenDay(_ date: Date?) -> String {
    guard let date else { return "resets later" }
    let f = DateFormatter()
    f.dateFormat = "d MMM"
    return "resets \(f.string(from: date))"
}

extension Color {
    static let orangeBrand = Color(red: 217 / 255, green: 119 / 255, blue: 87 / 255)
    static let peachBrand  = Color(red: 255 / 255, green: 184 / 255, blue: 146 / 255)
}

#Preview(as: .systemMedium) {
    ClaudeUsageWidget()
} timeline: {
    UsageEntry(date: Date(), state: .loaded(.placeholder))
}
