import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView } from 'react-native';

const HomeScreen = ({ navigation }: any) => {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.statusCard}>
        <Text style={styles.statusTitle}>System Status</Text>
        <Text style={styles.statusActive}>🟢 AI Auditors Online</Text>
        <Text style={styles.statusText}>Local Vector DB: Encrypted</Text>
      </View>

      <View style={styles.buttonContainer}>
      <TouchableOpacity 
          style={styles.callButton}
          onPress={() => navigation.navigate('Call')}
        >
          <Text style={styles.buttonText}>Simulate Incoming Call</Text>
        </TouchableOpacity>
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