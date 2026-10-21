import SwiftUI

// Original generic hit-testing fixture. No SDK, endpoints, credentials or product code.
@main
struct InteractionProbe: App {
    var body: some Scene { WindowGroup { Content() } }
}
struct Content: View {
    @State private var count = 0
    @State private var provider = 2
    var body: some View {
        TabView {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    ForEach(0..<12) { index in
                        Text("Placeholder row \(index)").frame(height: 60)
                    }
                    Picker("Provider", selection: $provider) {
                        Text("First").tag(0)
                        Text("Second").tag(1)
                        Text("Third").tag(2)
                    }.pickerStyle(.segmented)
                    Button {
                        count += 1
                        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                            .appendingPathComponent("handler-count.txt")
                        try? String(count).write(to: url, atomically: true, encoding: .utf8)
                    }
                    label: {
                        Label("Activate diagnostic action", systemImage: "person.badge.key")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("probe.activate")
                    Text("Handler count: \(count)").accessibilityIdentifier("probe.count")
                    ForEach(12..<20) { index in
                        Text("Placeholder row \(index)").frame(height: 60)
                    }
                }.padding()
            }.navigationTitle("Interaction probe")
                .navigationBarTitleDisplayMode(.inline)
        }.tabItem { Label("Action", systemImage: "person") }
        Text("Second tab").tabItem { Label("Other", systemImage: "gear") }
        }
    }
}
