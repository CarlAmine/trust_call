import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, Button, PermissionsAndroid, Platform, Alert } from 'react-native';

const DEMO_INCOMING_CALL = {
  callerId: 'alice_demo',
  callerName: 'Alice Demo',
};

const requestCallPermissions = async () => {
  if (Platform.OS !== 'android') return true;

  try {
    const granted = await PermissionsAndroid.requestMultiple([
      PermissionsAndroid.PERMISSIONS.CAMERA,
      PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
    ]);

    const cameraGranted = granted['android.permission.CAMERA'] === PermissionsAndroid.RESULTS.GRANTED;
    const audioGranted = granted['android.permission.RECORD_AUDIO'] === PermissionsAndroid.RESULTS.GRANTED;

    if (cameraGranted && audioGranted) {
      console.log('Permissions granted! Safe to start WebRTC.');
      return true;
    } else {
      Alert.alert('Permissions Required', 'Trust-Call Shield needs camera and microphone access to simulate the call.');
      return false;
    }
  } catch (err) {
    console.warn('Error requesting permissions:', err);
    return false;
  }
};

const HomeScreen = ({ navigation }: any) => {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.statusCard}>
        <Text style={styles.statusTitle}>System Status</Text>
        <Text style={styles.statusActive}>🟢 AI Auditors Online</Text>
        <Text style={styles.statusText}>Local Vector DB: Encrypted</Text>
      </View>

      <View style={styles.buttonContainer}>
        <Button 
          title="Simulate Incoming Call"
          onPress={async () => {
            const hasPermission = await requestCallPermissions();
            if (!hasPermission) return;

            navigation.navigate('CallScreen', DEMO_INCOMING_CALL); 
          }} 
        />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { 
    flex: 1, 
    backgroundColor: '#121212', 
    padding: 20 
  },
  statusCard: {
    backgroundColor: '#1E1E1E',
    padding: 20,
    borderRadius: 10,
    marginTop: 20,
    borderWidth: 1,
    borderColor: '#333'
  },
  statusTitle: { 
    color: '#888', 
    fontSize: 14, 
    textTransform: 'uppercase', 
    letterSpacing: 1 
  },
  statusActive: { 
    color: '#4CAF50', 
    fontSize: 20, 
    fontWeight: 'bold', 
    marginTop: 10 
  },
  statusText: { 
    color: '#CCC', 
    fontSize: 14, 
    marginTop: 5 
  },
  buttonContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center'
  },
  callButton: {
    backgroundColor: '#d9534f',
    paddingVertical: 15,
    paddingHorizontal: 40,
    borderRadius: 30,
    elevation: 5, // Android shadow
    shadowColor: '#000', // iOS shadow
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
  },
  buttonText: {
    color: 'white',
    fontSize: 18,
    fontWeight: 'bold'
  }
});

export default HomeScreen;
