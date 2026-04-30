import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, PermissionsAndroid, Platform } from 'react-native';
import { mediaDevices, RTCPeerConnection, RTCSessionDescription } from 'react-native-webrtc';
import { getBackendHttpUrl, getBackendWsUrl, getResolvedBackendBaseUrl } from '../config/backend';


const CallScreen = ({ navigation, route }: any) => {
  const [callDuration, setCallDuration] = useState(0);
  const [localStream, setLocalStream] = useState<any>(null);
  const callerName = route?.params?.callerName ?? 'Unknown Caller';
  const callerId = route?.params?.callerId ?? 'unknown';
  
  // Phase 2: New State Variables for WebRTC Pipe
  const [peerConnection, setPeerConnection] = useState<any>(null);
  const [sdpOffer, setSdpOffer] = useState<string>('');

  // Phase 3: Telemetry State Variables
  const [signalScore, setSignalScore] = useState<string>('Analyzing...');
  const [semanticStatus, setSemanticStatus] = useState<string>('Pending...');
  const [identityStatus, setIdentityStatus] = useState<string>('Pending...');
  const [identityConfidence, setIdentityConfidence] = useState<string>('Pending...');
  const [identityMode, setIdentityMode] = useState<string>('Pending...');
  const [identifiedCaller, setIdentifiedCaller] = useState<string>('Pending...');
  const [identityChunks, setIdentityChunks] = useState<number>(0);
  const [identityReason, setIdentityReason] = useState<string>('Awaiting live audio...');
  const [audioFrames, setAudioFrames] = useState<number>(0);
  const [bufferedSeconds, setBufferedSeconds] = useState<string>('0.00s');
  const [fusionStatus, setFusionStatus] = useState<string>('WAITING');
  const [sessionId, setSessionId] = useState<string>('Not Connected');
  const [telemetryStatus, setTelemetryStatus] = useState<string>('Disconnected');

  const [signalColor, setSignalColor] = useState<string>('#4CAF50'); // Default Green

  const [isCallActive, setIsCallActive] = useState(false);
  
  const ws = useRef<WebSocket | null>(null);

  const formatPercent = (value: unknown): string => {
    if (value == null || value === '') {
      return 'Pending...';
    }
    const numeric = Number(value);
    return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(1)}%` : String(value);
  };

  const formatSessionId = (value: string): string => {
    if (!value || value === 'Not Connected' || value === 'Unknown Session') {
      return value;
    }
    return value.slice(0, 8);
  };

  const applyIdentityTelemetry = (payload: any, chunkCount?: number) => {
    const identityText =
      payload.identity_match ??
      payload.display_text ??
      payload.status ??
      'Pending...';
    const confidence =
      payload.identity_match_confidence ??
      payload.match_confidence ??
      null;
    const mode =
      payload.identity_mode ??
      payload.identification_mode ??
      'verification';
    const identified =
      payload.identity_identified_caller_id ??
      payload.identified_caller_id ??
      'No candidate';
    const reason =
      payload.identity_reason ??
      payload.reason ??
      'No runtime issue reported';

    setIdentityStatus(String(identityText));
    setIdentityConfidence(formatPercent(confidence));
    setIdentityMode(String(mode));
    setIdentifiedCaller(String(identified));
    setIdentityReason(String(reason));
    if (typeof chunkCount === 'number') {
      setIdentityChunks(chunkCount);
    }
  };

  const applySessionSnapshot = (session: any) => {
    setTelemetryStatus((current) => (current === 'Connected' ? 'Connected + Polling' : 'Polling'));
    setAudioFrames(typeof session.frames_received === 'number' ? session.frames_received : 0);
    setBufferedSeconds(
      typeof session.buffered_duration_seconds === 'number'
        ? `${session.buffered_duration_seconds.toFixed(2)}s`
        : '0.00s'
    );
    setIdentityChunks(typeof session.chunks_processed === 'number' ? session.chunks_processed : 0);

    if (session.last_signal_score) {
      setSignalScore(session.last_signal_score);
      setSignalColor(session.last_signal_threat ? '#FF3B30' : '#4CAF50');
    }

    if (session.last_identity_result) {
      applyIdentityTelemetry(session.last_identity_result, session.chunks_processed);
      setFusionStatus(
        session.state === 'telemetry_broadcast'
          ? 'ANALYZING'
          : String(session.state ?? 'ANALYZING').toUpperCase()
      );
      return;
    }

    setIdentityReason(session.last_error ?? session.state ?? 'Awaiting live audio...');
  };

  const startAudioStream = async () => {
    try {
      // 1. PERMISSIONS
      if (Platform.OS === 'android') {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          {
            title: 'Trust-Call Microphone Permission',
            message: 'Trust-Call needs access to your microphone to analyze the call audio for threats.',
            buttonNeutral: 'Ask Me Later',
            buttonNegative: 'Cancel',
            buttonPositive: 'OK',
          },
        );
        if (granted !== PermissionsAndroid.RESULTS.GRANTED) {
          console.log('Microphone permission denied');
          return;
        }
      }

      console.log('1. Permission granted! Initializing WebRTC stream...');
      console.log(`Using Trust-Call backend at ${getResolvedBackendBaseUrl()}`);
      
      // --- THE FIX 1: Revert to standard audio to prevent the "Dummy Track" bug ---
      const stream = await mediaDevices.getUserMedia({
        audio: true, 
        video: false, 
      });
      setLocalStream(stream);
      // -------------------------------------------------------------------------

      // 2. WEBRTC HANDSHAKE
      console.log('2. Building Peer Connection...');
      const configuration = {
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
      };
      const pc = new RTCPeerConnection(configuration);
      setPeerConnection(pc);

      stream.getTracks().forEach((track: any) => {
        pc.addTrack(track, stream);
      });

      console.log('3. Generating SDP Offer for Python Server...');
      const offer = await pc.createOffer({});
      await pc.setLocalDescription(offer);
      
      setSdpOffer(offer.sdp);
      console.log('OFFER GENERATED SUCCESSFULLY!');

      console.log('4. Sending Offer to Python Server...');
      try {
        const response = await fetch(getBackendHttpUrl('/offer'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sdp: offer.sdp,
            type: offer.type,
            caller_id: callerId,
          }),
        });

        const answer = await response.json();
        console.log('5. Received Answer from Python Server!');
        setSessionId(answer.session_id ?? 'Unknown Session');

        await pc.setRemoteDescription(
          new RTCSessionDescription({
            sdp: answer.sdp,
            type: answer.type,
          })
        );
        console.log('🟢 HANDSHAKE COMPLETE! Live audio is now flowing to Python.');

        // --- THE FIX 2: Open the WebSocket strictly AFTER audio is flowing ---
        console.log('6. Opening Telemetry WebSocket...');
        ws.current = new WebSocket(getBackendWsUrl('/ws')); 
        
        ws.current.onopen = () => {
          console.log('🔗 WebSocket Connected to Telemetry Stream');
          setTelemetryStatus('Connected');
        };
        
        ws.current.onmessage = (e) => {
          try {
            console.log("🔥 WEBSOCKET MESSAGE RECEIVED: ", e.data);
            const data = JSON.parse(e.data);
            setTelemetryStatus('Connected');
            setSignalScore(data.signal_score);
            // If it's a threat, turn the text Red. Otherwise, keep it Green.
            setSignalColor(data.is_threat ? '#FF3B30' : '#4CAF50'); 

            setSemanticStatus(data.semantic_intent);
            applyIdentityTelemetry(data, data.identity_chunk_count);
            setFusionStatus(data.fusion_status);
          } catch (error) {
            console.error("Error parsing telemetry data", error);
          }
        };
        
        ws.current.onerror = (e: any) => {
          console.log('❌ WebSocket Error: ', e.message);
          setTelemetryStatus('Error');
        };
        ws.current.onclose = () => {
          console.log('Telemetry WebSocket closed');
          setTelemetryStatus('Closed');
        };
        // ---------------------------------------------------------------------

      } catch (networkError) {
        console.error('Failed to connect to Python server. Is uvicorn running?', networkError);
      }
      
    } catch (error) {
      console.error('Error starting audio stream:', error);
    }
  };

const handleAcceptCall = () => {
    setIsCallActive(true);
    startAudioStream();
  };

  useEffect(() => {
    let timer: ReturnType<typeof setInterval>;
    if (isCallActive) {
      timer = setInterval(() => {
        setCallDuration((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isCallActive]);

  useEffect(() => {
    if (!isCallActive || sessionId === 'Not Connected' || sessionId === 'Unknown Session') {
      return;
    }

    let cancelled = false;

    const pollSession = async () => {
      try {
        const response = await fetch(getBackendHttpUrl(`/identity/live/sessions/${sessionId}`));
        if (!response.ok) {
          return;
        }
        const session = await response.json();
        if (!cancelled) {
          applySessionSnapshot(session);
        }
      } catch (error) {
        console.log('Live session polling failed:', error);
      }
    };

    pollSession();
    const pollTimer = setInterval(pollSession, 1500);

    return () => {
      cancelled = true;
      clearInterval(pollTimer);
    };
  }, [isCallActive, sessionId]);

  
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };
  
  const handleEndCall = () => {
    if (localStream) {
      localStream.getTracks().forEach((track: any) => track.stop());
    }
    if (peerConnection) {
      peerConnection.close();
    }
    // --- NEW: Close the socket ---
    if (ws.current) {
      ws.current.close();
    }
    // -----------------------------
    navigation.navigate('HomeScreen');
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.callerName}>{callerName}</Text>
        <Text style={styles.callTime}>{formatTime(callDuration)}</Text>
        <Text style={styles.sessionMeta}>Session: {formatSessionId(sessionId)}</Text>
        <Text style={styles.sessionMeta}>Telemetry: {telemetryStatus}</Text>
      </View>

      <View style={styles.telemetryBoard}>
        <Text style={styles.boardTitle}>Live AI Telemetry</Text>
        
        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Signal</Text>
          <Text style={[styles.metricValueSafe, { color: signalColor }]}>{signalScore}</Text>
        </View>
        
        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Semantic</Text>
          <Text style={styles.metricValueSafe}>{semanticStatus}</Text>
        </View>

        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Identity</Text>
          <Text style={styles.metricValueWarning}>{identityStatus}</Text>
        </View>

        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Confidence</Text>
          <Text style={styles.metricValueSafe}>{identityConfidence}</Text>
        </View>

        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Mode</Text>
          <Text style={styles.metricValueSafe}>{identityMode}</Text>
        </View>

        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Candidate</Text>
          <Text style={styles.metricValueSafe}>{identifiedCaller}</Text>
        </View>

        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Chunks</Text>
          <Text style={styles.metricValueSafe}>{identityChunks}</Text>
        </View>

        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Frames</Text>
          <Text style={styles.metricValueSafe}>{audioFrames}</Text>
        </View>

        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Buffered</Text>
          <Text style={styles.metricValueSafe}>{bufferedSeconds}</Text>
        </View>

        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Reason</Text>
          <Text style={styles.metricValueSubtle}>{identityReason}</Text>
        </View>
      </View>

      <View style={styles.decisionEngine}>
        <Text style={styles.decisionLabel}>Late Fusion Status</Text>
        <Text style={styles.decisionSafe}>{fusionStatus}</Text>
      </View>

<View style={styles.footer}>
        {!isCallActive ? (
          <TouchableOpacity 
            style={[styles.endCallButton, { backgroundColor: '#4CAF50' }]} 
            onPress={handleAcceptCall}
          >
            <Text style={styles.endCallText}>Accept</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity 
            style={styles.endCallButton}
            onPress={handleEndCall}
          >
            <Text style={styles.endCallText}>End Call</Text>
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000', padding: 20 },
  header: { alignItems: 'center', marginTop: 40, marginBottom: 40 },
  callerName: { color: '#FFF', fontSize: 32, fontWeight: 'bold' },
  callTime: { color: '#888', fontSize: 18, marginTop: 10 },
  sessionMeta: { color: '#666', fontSize: 12, marginTop: 8 },
  
  telemetryBoard: { backgroundColor: '#1A1A1A', padding: 20, borderRadius: 15, borderWidth: 1, borderColor: '#333' },
  boardTitle: { color: '#555', fontSize: 12, textTransform: 'uppercase', marginBottom: 15, letterSpacing: 1 },
  metricRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15, gap: 12 },
  metricLabel: { color: '#CCC', fontSize: 16, width: 92 },
  metricValueSafe: { color: '#4CAF50', fontSize: 16, fontWeight: 'bold', flex: 1, textAlign: 'right' },
  metricValueWarning: { color: '#FFC107', fontSize: 16, fontWeight: 'bold', flex: 1, textAlign: 'right' },
  metricValueSubtle: { color: '#AAA', fontSize: 14, fontWeight: '500', flex: 1, textAlign: 'right' },
  
  decisionEngine: { alignItems: 'center', marginTop: 40 },
  decisionLabel: { color: '#888', fontSize: 14, textTransform: 'uppercase' },
  decisionSafe: { color: '#00BCD4', fontSize: 24, fontWeight: 'bold', marginTop: 10, letterSpacing: 2 },
  
  footer: { flex: 1, justifyContent: 'flex-end', alignItems: 'center', marginBottom: 30 },
  endCallButton: { backgroundColor: '#FF3B30', width: 80, height: 80, borderRadius: 40, justifyContent: 'center', alignItems: 'center' },
  endCallText: { color: '#FFF', fontWeight: 'bold', fontSize: 16 }
});

export default CallScreen;
