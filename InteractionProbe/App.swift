import SwiftUI

// Original generic hit-testing fixture. No SDK, endpoints, credentials or product code.
@main
struct InteractionProbe: App {
    var body: some Scene { WindowGroup { Content() } }
}
struct Content: View {
    @State private var count = 0
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    ForEach(0..<12) { index in
                        Text("Placeholder row \(index)").frame(height: 60)
                    }
                    Button("Activate diagnostic action") {
                        count += 1
                        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                            .appendingPathComponent("handler-count.txt")
                        try? String(count).write(to: url, atomically: true, encoding: .utf8)
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("probe.activate")
                    Text("Handler count: \(count)").accessibilityIdentifier("probe.count")
                    ForEach(12..<20) { index in
                        Text("Placeholder row \(index)").frame(height: 60)
                    }
                }.padding()
            }.navigationTitle("Interaction probe")
        }
    }
}
