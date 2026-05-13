import SwiftUI

/// Renders a Liquid Glass preview of the widget inside the host app so users can see
/// the result without leaving the app. Mirrors the widget's WidgetView layout — same
/// glass cards, same accent. The wallpaper-aware translucency naturally falls back to
/// a tinted material in this in-app preview since there's no home-screen wallpaper.
struct WidgetPreviewCard: View {
    let loaded: WidgetState.Loaded?

    var body: some View {
        ZStack {
            // Layered background so the glass has something tinted to refract.
            LinearGradient(
                colors: [Color(red: 0.30, green: 0.18, blue: 0.12),
                         Color(red: 0.18, green: 0.12, blue: 0.10)],
                startPoint: .topLeading, endPoint: .bottomTrailing,
            )
            RadialGradient(
                gradient: Gradient(colors: [Color.orangeBrandApp.opacity(0.35), .clear]),
                center: .init(x: 0.85, y: 0.15), startRadius: 0, endRadius: 240,
            )
            if let loaded {
                PreviewBody(loaded: loaded).padding(14)
            } else {
                emptyOverlay
            }
        }
    }

    private var emptyOverlay: some View {
        VStack(spacing: 6) {
            Image(systemName: "rectangle.on.rectangle.angled")
                .font(.title2)
                .foregroundStyle(.white.opacity(0.7))
            Text("No data yet")
                .font(.callout)
                .foregroundStyle(.white.opacity(0.7))
        }
    }
}

private struct PreviewBody: View {
    let loaded: WidgetState.Loaded

    var body: some View {
        GeometryReader { geo in
            let headerH: CGFloat = 24
            let gap: CGFloat = 10
            let bodyH = geo.size.height - headerH - gap
            VStack(spacing: gap) {
                PreviewHeader(loaded: loaded).frame(height: headerH)
                HStack(spacing: gap) {
                    PreviewRing(percent: loaded.fiveHourPct, label: "5-hour", empty: false)
                    PreviewRing(percent: loaded.sevenDayPct ?? 0, label: loaded.sevenDayLabel, empty: loaded.sevenDayPct == nil)
                    PreviewCountdown(resetsAt: loaded.fiveHourResetsAt)
                }
                .frame(height: bodyH)
            }
        }
    }
}

private struct PreviewHeader: View {
    let loaded: WidgetState.Loaded
    var body: some View {
        HStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(
                        LinearGradient(
                            colors: [Color.peachBrandApp, Color.orangeBrandApp],
                            startPoint: .topLeading, endPoint: .bottomTrailing,
                        )
                    )
                    .frame(width: 20, height: 20)
                    .shadow(color: Color.orangeBrandApp.opacity(0.7), radius: 4)
                Text("C")
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(.white)
            }
            Text("Claude Usage")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(.white)
            Spacer()
            Text(rightLabel)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(.white.opacity(0.75))
        }
    }
    private var rightLabel: String {
        let f = DateFormatter(); f.dateFormat = "HH:mm"
        let t = f.string(from: loaded.fetchedAt)
        return loaded.mock ? "Opus · \(t) · MOCK" : "Opus · \(t)"
    }
}

private struct PreviewRing: View {
    let percent: Double
    let label: String
    let empty: Bool
    var body: some View {
        GeometryReader { geo in
            let d = min(82, min(geo.size.width - 4, geo.size.height - 28))
            let stroke: CGFloat = max(7, d * 0.11)
            VStack(spacing: 6) {
                ZStack {
                    Circle().stroke(Color.white.opacity(0.15), lineWidth: stroke).frame(width: d, height: d)
                    if !empty {
                        Circle().trim(from: 0, to: max(0, min(percent / 100, 1)))
                            .stroke(
                                AngularGradient(
                                    colors: [Color.orangeBrandApp, Color.peachBrandApp, Color.orangeBrandApp],
                                    center: .center,
                                    startAngle: .degrees(-90),
                                    endAngle: .degrees(270),
                                ),
                                style: StrokeStyle(lineWidth: stroke, lineCap: .round),
                            )
                            .rotationEffect(.degrees(-90))
                            .frame(width: d, height: d)
                            .shadow(color: Color.orangeBrandApp.opacity(0.65), radius: 8)
                    }
                    if empty {
                        Text("—").font(.system(size: d * 0.20, weight: .bold)).foregroundStyle(.white.opacity(0.5))
                    } else {
                        Text("\(Int(percent.rounded()))%").font(.system(size: d * 0.24, weight: .bold)).foregroundStyle(.white)
                    }
                }
                Text(label.uppercased())
                    .font(.system(size: 9, weight: .bold))
                    .tracking(0.6)
                    .foregroundStyle(.white.opacity(0.75))
            }
            .frame(maxWidth: .infinity)
        }
    }
}

private struct PreviewCountdown: View {
    let resetsAt: Date?
    var body: some View {
        VStack(spacing: 2) {
            Text("RESETS IN")
                .font(.system(size: 10, weight: .bold))
                .tracking(0.8)
                .foregroundStyle(.white.opacity(0.7))
                .padding(.top, 12)
            Text(formatCountdownApp(resetsAt))
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(Color.peachBrandApp)
                .minimumScaleFactor(0.7)
                .lineLimit(1)
                .padding(.horizontal, 4)
            Text("5-hour window")
                .font(.system(size: 9))
                .foregroundStyle(.white.opacity(0.55))
                .padding(.top, 2)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity)
        .modifier(PreviewGlass(cornerRadius: 16))
    }
}

private struct PreviewGlass: ViewModifier {
    let cornerRadius: CGFloat
    func body(content: Content) -> some View {
        // See WidgetView.GlassPanel — `.glassEffect` swallows content on iOS 26.4.
        // Using `.background(.regularMaterial, in:)` gives Liquid Glass without that.
        content
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .strokeBorder(Color.orangeBrandApp.opacity(0.30), lineWidth: 1)
            )
    }
}

private func formatCountdownApp(_ date: Date?) -> String {
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

extension Color {
    static let orangeBrandApp = Color(red: 217 / 255, green: 119 / 255, blue: 87 / 255)
    static let peachBrandApp  = Color(red: 255 / 255, green: 184 / 255, blue: 146 / 255)
}
