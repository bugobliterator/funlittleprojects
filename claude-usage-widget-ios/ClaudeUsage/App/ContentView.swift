import SwiftUI
import WidgetKit

struct ContentView: View {
    @StateObject private var vm = ConfigViewModel()
    @State private var showingLogin = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    header
                    accountSection
                    previewSection
                    Color.clear.frame(height: 20)
                }
                .padding(.horizontal, 20)
                .padding(.top, 16)
            }
            .navigationTitle("Claude Usage")
            .background(Color(uiColor: .systemGroupedBackground))
            .sheet(isPresented: $showingLogin) {
                LoginView { sessionKey, orgId, userAgent in
                    vm.completeLogin(sessionKey: sessionKey, orgId: orgId, userAgent: userAgent)
                }
            }
            .task { await vm.refreshIfPossible() }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Configure widget")
                .font(.title3.weight(.semibold))
            Text("Tap log in and sign into your Claude account. The widget reads your usage page every 15 minutes. Session cookies live in the iOS Keychain.")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
    }

    private var accountSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionLabel("Account")

            HStack(spacing: 10) {
                Circle()
                    .fill(vm.statusColor)
                    .frame(width: 10, height: 10)
                Text(vm.statusText)
                    .font(.callout)
            }
            .padding(.bottom, 4)

            HStack(spacing: 12) {
                if vm.isLoggedIn {
                    Button("Log out", role: .destructive) { vm.logout() }
                        .buttonStyle(.bordered)
                } else {
                    Button("Log in to Claude") { showingLogin = true }
                        .buttonStyle(.borderedProminent)
                }
                Button("Refresh now") {
                    Task { await vm.refreshNow() }
                }
                .buttonStyle(.bordered)
                .disabled(!vm.canRefresh)
            }

            Toggle("Use mock data", isOn: $vm.useMock)
                .onChange(of: vm.useMock) { _, newValue in
                    vm.applyMockToggle(newValue)
                }
                .padding(.top, 4)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }

    private var previewSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionLabel("Preview")
            WidgetPreviewCard(loaded: vm.previewLoaded)
                .frame(height: 160)
                .clipShape(RoundedRectangle(cornerRadius: 18))
            Text(vm.previewCaption)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }

    private func sectionLabel(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.caption.weight(.semibold))
            .foregroundStyle(.secondary)
            .tracking(0.8)
    }
}
