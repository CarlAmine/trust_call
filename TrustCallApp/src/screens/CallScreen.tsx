import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView } from 'react-native';

const CallScreen = ({ navigation }: any) => {
  // Simulating the real-time threat scores we will eventually get from the EEP Gateway
  const [callDuration, setCallDuration] = useState(0);

  // Simple timer to simulate call duration
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
          onPress={() => navigation.navigate('Home')}
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
  
  telemetryBoard: { 
    backgroundColor: '#1A1A1A', 
    padding: 20, 
    borderRadius: 15, 
    borderWidth: 1, 
    borderColor: '#333' 
  },
  boardTitle: { color: '#555', fontSize: 12, textTransform: 'uppercase', marginBottom: 15, letterSpacing: 1 },
  metricRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 15 },
  metricLabel: { color: '#CCC', fontSize: 16 },
  metricValueSafe: { color: '#4CAF50', fontSize: 16, fontWeight: 'bold' },
  metricValueWarning: { color: '#FFC107', fontSize: 16, fontWeight: 'bold' },
  
  decisionEngine: { alignItems: 'center', marginTop: 40 },
  decisionLabel: { color: '#888', fontSize: 14, textTransform: 'uppercase' },
  decisionSafe: { color: '#00BCD4', fontSize: 24, fontWeight: 'bold', marginTop: 10, letterSpacing: 2 },
  
  footer: { flex: 1, justifyContent: 'flex-end', alignItems: 'center', marginBottom: 30 },
  endCallButton: { 
    backgroundColor: '#FF3B30', 
    width: 80, 
    height: 80, 
    borderRadius: 40, 
    justifyContent: 'center', 
    alignItems: 'center' 
  },
  endCallText: { color: '#FFF', fontWeight: 'bold', fontSize: 16 }
});

export default CallScreen;