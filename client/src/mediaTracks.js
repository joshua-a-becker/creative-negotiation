// Central registry of every getUserMedia stream the app opens.
//
// The browser camera/mic "recording" indicator stays lit until EVERY track
// across ALL streams reads readyState === "ended". A single orphaned stream —
// a device-selector preview, a getUserMedia retry, a React double-mount — keeps
// it on, and if nothing holds a reference to that stream, no component cleanup
// can reach it. Routing every getUserMedia through here lets teardown stop them
// all unconditionally.

const liveStreams = new Set();

// Drop-in replacement for navigator.mediaDevices.getUserMedia that registers the
// resulting stream. Use this everywhere instead of calling getUserMedia directly.
export async function getTrackedUserMedia(constraints) {
  const stream = await navigator.mediaDevices.getUserMedia(constraints);
  liveStreams.add(stream);
  // Self-evict once all of this stream's tracks have ended on their own.
  stream.getTracks().forEach((t) =>
    t.addEventListener("ended", () => {
      if (stream.getTracks().every((x) => x.readyState === "ended")) {
        liveStreams.delete(stream);
      }
    })
  );
  return stream;
}

// Stop every tracked stream. This is what actually turns the indicator off.
export function stopAllTrackedStreams() {
  liveStreams.forEach((stream) =>
    stream.getTracks().forEach((t) => {
      try {
        t.stop();
      } catch {
        /* already ended */
      }
    })
  );
  liveStreams.clear();
}

// Diagnostic: list every tracked track and its readyState. Anything still "live"
// is what's holding the indicator. Also reachable from the console via
// window.__mediaTracks.dump().
export function dumpTrackStates() {
  const rows = [];
  liveStreams.forEach((s) =>
    s.getTracks().forEach((t) =>
      rows.push({ kind: t.kind, readyState: t.readyState, label: t.label })
    )
  );
  // eslint-disable-next-line no-console
  console.table(rows);
  return rows;
}

if (typeof window !== "undefined") {
  window.__mediaTracks = { dump: dumpTrackStates, stopAll: stopAllTrackedStreams };
}
