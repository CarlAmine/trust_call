import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, PermissionsAndroid, Platform } from 'react-native';
import { mediaDevices, RTCPeerConnection, RTCSessionDescription } from 'react-native-webrtc';

const CallScreen = ({ navigation }: any) => {
  const [callDuration, setCallDuration] = useState(0);
  const [localStream, setLocalStream] = useState<any>(null);
  
  // Phase 2: New State Variables for WebRTC Pipe
  const [peerConnection, setPeerConnection] = useState<any>(null);
  const [sdpOffer, setSdpOffer] = useState<string>('');

  const startAudioStream = async () => {
    try {
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
      const stream = await mediaDevices.getUserMedia({
        audio: true,
        video: false, 
      });
      setLocalStream(stream);

      // Phase 2: Building the WebRTC Pipe
      console.log('2. Building Peer Connection...');
      const configuration = {
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
      };
      const pc = new RTCPeerConnection(configuration);
      setPeerConnection(pc);

      // Phase 2: Attach the live microphone audio
      stream.getTracks().forEach((track: any) => {
        pc.addTrack(track, stream);
      });

      // Phase 2: Generate the Handshake Contract (Offer)
      console.log('3. Generating SDP Offer for Python Server...');
      const offer = await pc.createOffer({});
      await pc.setLocalDescription(offer);
      
      setSdpOffer(offer.sdp);
      console.log('OFFER GENERATED SUCCESSFULLY!');

      console.log('4. Sending Offer to Python Server...');
      try {
        // 10.0.2.2 is the magic IP that lets the Android emulator see your computer's localhost
        const response = await fetch('http://10.0.2.2:8080/offer', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            sdp: offer.sdp,
            type: offer.type,
          }),
        });

        // Parse the answer we get back from Python
        const answer = await response.json();
        console.log('5. Received Answer from Python Server!');

        // Complete the WebRTC handshake!
        await pc.setRemoteDescription(new RTCSessionDescription(answer));
        console.log('🟢 HANDSHAKE COMPLETE! Live audio is now flowing to Python.');

      } catch (networkError) {
        console.error('Failed to connect to Python server. Is uvicorn running?', networkError);
      }
      
    } catch (error) {
      console.error('Error starting audio stream:', error);
    }
  };

  useEffect(() => {
    startAudioStream();
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      setCallDuration((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

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
    navigation.navigate('HomeScreen');
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.callerName}>Unknown Caller</Text>
        <Text style={styles.callTime}>{formatTime(callDuration)}</Text>
      </View>

      <View style={styles.telemetryBoard}>
        <Text style={styles.boardTitle}>Live AI Telemetry</Text>
        
        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Signal (RawNet2):</Text>
          <Text style={styles.metricValueSafe}>1.2% Spoof</Text>
        </View>
        
        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Semantic (Intent):</Text>
          <Text style={styles.metricValueSafe}>Low Risk</Text>
        </View>

        <View style={styles.metricRow}>
          <Text style={styles.metricLabel}>Identity (ECAPA):</Text>
          <Text style={styles.metricValueWarning}>Pending...</Text>
        </View>
      </View>

      <View style={styles.decisionEngine}>
        <Text style={styles.decisionLabel}>Late Fusion Status</Text>
        <Text style={styles.decisionSafe}>ANALYZING</Text>
      </View>

      <View style={styles.footer}>
        <TouchableOpacity 
          style={styles.endCallButton}
          onPress={handleEndCall}
        >
          <Text style={styles.endCallText}>End Call</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000', padding: 20 },
  header: { alignItems: 'center', marginTop: 40, marginBottom: 40 },
  callerName: { color: '#FFF', fontSize: 32, fontWeight: 'bold' },
  callTime: { color: '#888', fontSize: 18, marginTop: 10 },
  
  telemetryBoard: { backgroundColor: '#1A1A1A', padding: 20, borderRadius: 15, borderWidth: 1, borderColor: '#333' },
  boardTitle: { color: '#555', fontSize: 12, textTransform: 'uppercase', marginBottom: 15, letterSpacing: 1 },
  metricRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 15 },
  metricLabel: { color: '#CCC', fontSize: 16 },
  metricValueSafe: { color: '#4CAF50', fontSize: 16, fontWeight: 'bold' },
  metricValueWarning: { color: '#FFC107', fontSize: 16, fontWeight: 'bold' },
  
  decisionEngine: { alignItems: 'center', marginTop: 40 },
  decisionLabel: { color: '#888', fontSize: 14, textTransform: 'uppercase' },
  decisionSafe: { color: '#00BCD4', fontSize: 24, fontWeight: 'bold', marginTop: 10, letterSpacing: 2 },
  
  footer: { flex: 1, justifyContent: 'flex-end', alignItems: 'center', marginBottom: 30 },
  endCallButton: { backgroundColor: '#FF3B30', width: 80, height: 80, borderRadius: 40, justifyContent: 'center', alignItems: 'center' },
  endCallText: { color: '#FFF', fontWeight: 'bold', fontSize: 16 }
});

export default CallScreen;