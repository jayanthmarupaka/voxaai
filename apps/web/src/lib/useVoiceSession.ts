"use client";

/**
 * Turn-based voice: the browser records with MediaRecorder, watches the mic
 * level with an AnalyserNode, and sends `end_of_turn` after a short silence.
 * True streaming STT is not viable on CPU Whisper, and pretending otherwise
 * would just add latency without adding interactivity.
 */

import { useCallback, useEffect, useRef, useState } from "react";

const SILENCE_RMS = 0.012;
const SILENCE_MS = 900;
const MIN_SPEECH_MS = 400;

export type VoiceState = "idle" | "connecting" | "listening" | "thinking" | "speaking";

type Options = {
  businessId: string;
  onTranscript: (text: string) => void;
  onReply: (text: string, intent: string, outcome: string) => void;
  onError: (message: string) => void;
};

export function useVoiceSession({ businessId, onTranscript, onReply, onError }: Options) {
  const [state, setState] = useState<VoiceState>("idle");
  const [level, setLevel] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const playheadRef = useRef(0);
  const sampleRateRef = useRef(22050);
  const rafRef = useRef<number | null>(null);
  const speechStartedRef = useRef(0);
  const silenceSinceRef = useRef<number | null>(null);
  const turnOpenRef = useRef(false);

  // Latest callbacks without re-opening the socket on every render.
  const handlers = useRef({ onTranscript, onReply, onError });
  useEffect(() => {
    handlers.current = { onTranscript, onReply, onError };
  }, [onTranscript, onReply, onError]);

  const stopPlayback = useCallback(() => {
    const context = playbackCtxRef.current;
    if (context) {
      void context.close();
      playbackCtxRef.current = null;
    }
    playheadRef.current = 0;
  }, []);

  const playPcm = useCallback((bytes: ArrayBuffer) => {
    let context = playbackCtxRef.current;
    if (!context || context.state === "closed") {
      context = new AudioContext();
      playbackCtxRef.current = context;
      playheadRef.current = context.currentTime;
    }

    const samples = new Int16Array(bytes);
    if (samples.length === 0) return;
    const buffer = context.createBuffer(1, samples.length, sampleRateRef.current);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i += 1) {
      channel[i] = samples[i] / 32768;
    }

    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    // Queue back-to-back so consecutive sentences don't click or overlap.
    const startAt = Math.max(context.currentTime, playheadRef.current);
    source.start(startAt);
    playheadRef.current = startAt + buffer.duration;
  }, []);

  const stop = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void audioCtxRef.current?.close();
    audioCtxRef.current = null;
    stopPlayback();
    socketRef.current?.close();
    socketRef.current = null;
    turnOpenRef.current = false;
    setState("idle");
    setLevel(0);
  }, [stopPlayback]);

  const endTurn = useCallback(() => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !turnOpenRef.current) return;
    turnOpenRef.current = false;
    silenceSinceRef.current = null;
    // Flush whatever MediaRecorder is holding before asking for a transcript.
    recorderRef.current?.requestData();
    setTimeout(() => socket.send(JSON.stringify({ type: "end_of_turn" })), 120);
    setState("thinking");
  }, []);

  const start = useCallback(async () => {
    setState("connecting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
      streamRef.current = stream;

      const base = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
      const socket = new WebSocket(`${base.replace(/\/$/, "")}/ws/voice/${businessId}`);
      socket.binaryType = "arraybuffer";
      socketRef.current = socket;

      socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          playPcm(event.data);
          return;
        }
        const message = JSON.parse(event.data as string);
        switch (message.type) {
          case "ready":
            sampleRateRef.current = message.sampleRate ?? 22050;
            setState("listening");
            break;
          case "transcript":
            handlers.current.onTranscript(message.text);
            break;
          case "reply":
            handlers.current.onReply(message.text, message.intent, message.outcome);
            break;
          case "speech_start":
            sampleRateRef.current = message.sampleRate ?? sampleRateRef.current;
            setState("speaking");
            break;
          case "speech_end":
            setState("listening");
            break;
          case "error":
            handlers.current.onError(message.message ?? "Something went wrong.");
            setState("listening");
            break;
        }
      };

      socket.onerror = () => handlers.current.onError("Lost the connection to the receptionist.");
      socket.onclose = () => stop();

      await new Promise<void>((resolve, reject) => {
        socket.onopen = () => resolve();
        setTimeout(() => reject(new Error("Timed out connecting.")), 10000);
      });

      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0 && socket.readyState === WebSocket.OPEN) {
          void event.data.arrayBuffer().then((buffer) => socket.send(buffer));
        }
      };
      recorder.start(250);

      const audioCtx = new AudioContext();
      audioCtxRef.current = audioCtx;
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 1024;
      audioCtx.createMediaStreamSource(stream).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);

      const tick = () => {
        analyser.getFloatTimeDomainData(samples);
        let sum = 0;
        for (const sample of samples) sum += sample * sample;
        const rms = Math.sqrt(sum / samples.length);
        setLevel(rms);

        const now = performance.now();
        if (rms > SILENCE_RMS) {
          if (!turnOpenRef.current) {
            turnOpenRef.current = true;
            speechStartedRef.current = now;
            // Barge-in: the customer talking over the reply stops it.
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: "cancel" }));
            }
            stopPlayback();
          }
          silenceSinceRef.current = null;
        } else if (turnOpenRef.current) {
          silenceSinceRef.current ??= now;
          const spoken = now - speechStartedRef.current;
          if (now - silenceSinceRef.current > SILENCE_MS && spoken > MIN_SPEECH_MS) {
            endTurn();
          }
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    } catch (cause) {
      handlers.current.onError(
        cause instanceof DOMException
          ? "Microphone permission is required for the voice demo."
          : (cause as Error).message,
      );
      stop();
    }
  }, [businessId, endTurn, playPcm, stop, stopPlayback]);

  const sendText = useCallback((text: string) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "text", text }));
      setState("thinking");
      return true;
    }
    return false;
  }, []);

  useEffect(() => stop, [stop]);

  return { state, level, start, stop, sendText, endTurn };
}
