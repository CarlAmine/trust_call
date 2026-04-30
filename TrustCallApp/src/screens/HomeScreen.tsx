import React, { useEffect, useState } from 'react';
import {
  Alert,
  PermissionsAndroid,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { getBackendHttpUrl } from '../config/backend';

type TrustedContact = {
  callerId: string;
  callerName: string;
  label: string;
};

type EnrollmentStatus = {
  caller_id: string;
  enrolled: boolean;
  embedding_dim?: number;
  updated_at_utc?: string | null;
  num_updates?: number;
};

const TRUSTED_CONTACTS: TrustedContact[] = [
  {
    callerId: 'alice_demo',
    callerName: 'Alice Demo',
    label: 'Primary demo profile',
  },
  {
    callerId: 'mom_demo',
    callerName: 'Mom Demo',
    label: 'Trusted family contact',
  },
  {
    callerId: 'bank_contact',
    callerName: 'Bank Contact',
    label: 'High-risk caller profile',
  },
];

const UNKNOWN_INCOMING_CALL = {
  callerId: 'unknown',
  callerName: 'Unknown Caller',
};

const requestCallPermissions = async () => {
  if (Platform.OS !== 'android') return true;

  try {
    const granted = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
      {
        title: 'Trust Call Microphone Permission',
        message: 'Trust Call needs microphone access to analyze live call audio.',
        buttonNeutral: 'Ask Me Later',
        buttonNegative: 'Cancel',
        buttonPositive: 'OK',
      },
    );

    if (granted === PermissionsAndroid.RESULTS.GRANTED) {
      return true;
    }

    Alert.alert(
      'Microphone Required',
      'Trust Call needs microphone access before it can verify the caller voice.',
    );
    return false;
  } catch (err) {
    console.warn('Error requesting permissions:', err);
    return false;
  }
};

const formatStatusDetail = (status?: EnrollmentStatus) => {
  if (!status) return 'Checking enrollment';
  if (!status.enrolled) return 'No voice profile yet';

  const updates = status.num_updates ?? 0;
  const dimensions = status.embedding_dim ? `${status.embedding_dim}D` : 'embedding';
  return `${dimensions} profile, ${updates} updates`;
};

const HomeScreen = ({ navigation }: any) => {
  const [selectedCallerId, setSelectedCallerId] = useState(TRUSTED_CONTACTS[0].callerId);
  const [enrollmentByCallerId, setEnrollmentByCallerId] = useState<
    Record<string, EnrollmentStatus | undefined>
  >({});
  const [backendStatus, setBackendStatus] = useState('Checking backend');

  const selectedContact =
    TRUSTED_CONTACTS.find((contact) => contact.callerId === selectedCallerId) ??
    TRUSTED_CONTACTS[0];

  const refreshEnrollmentStatuses = async () => {
    setBackendStatus('Checking backend');
    try {
      const entries = await Promise.all(
        TRUSTED_CONTACTS.map(async (contact) => {
          const response = await fetch(
            getBackendHttpUrl(`/identity/enrollment/${contact.callerId}`),
          );
          if (!response.ok) {
            throw new Error(`Enrollment lookup failed for ${contact.callerId}`);
          }
          const status = (await response.json()) as EnrollmentStatus;
          return [contact.callerId, status] as const;
        }),
      );

      setEnrollmentByCallerId(Object.fromEntries(entries));
      setBackendStatus('AI auditors online');
    } catch (error) {
      console.warn('Failed to refresh enrollment statuses:', error);
      setBackendStatus('Backend offline');
    }
  };

  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', refreshEnrollmentStatuses);
    refreshEnrollmentStatuses();
    return unsubscribe;
  }, [navigation]);

  const startSelectedContactCall = async () => {
    const hasPermission = await requestCallPermissions();
    if (!hasPermission) return;

    navigation.navigate('CallScreen', {
      callerId: selectedContact.callerId,
      callerName: selectedContact.callerName,
    });
  };

  const startUnknownCallerCall = async () => {
    const hasPermission = await requestCallPermissions();
    if (!hasPermission) return;

    navigation.navigate('CallScreen', UNKNOWN_INCOMING_CALL);
  };

  const selectedStatus = enrollmentByCallerId[selectedContact.callerId];

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.statusCard}>
          <Text style={styles.statusTitle}>System Status</Text>
          <Text
            style={[
              styles.statusActive,
              backendStatus === 'Backend offline' && styles.statusOffline,
            ]}>
            {backendStatus}
          </Text>
          <Text style={styles.statusText}>Local speaker profiles: encrypted JSON store</Text>
        </View>

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Trusted Contacts</Text>
          <TouchableOpacity style={styles.refreshButton} onPress={refreshEnrollmentStatuses}>
            <Text style={styles.refreshButtonText}>Refresh</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.contactList}>
          {TRUSTED_CONTACTS.map((contact) => {
            const status = enrollmentByCallerId[contact.callerId];
            const isSelected = contact.callerId === selectedContact.callerId;
            const isEnrolled = status?.enrolled === true;

            return (
              <TouchableOpacity
                key={contact.callerId}
                style={[styles.contactCard, isSelected && styles.contactCardSelected]}
                onPress={() => setSelectedCallerId(contact.callerId)}>
                <View style={styles.contactTextBlock}>
                  <Text style={styles.contactName}>{contact.callerName}</Text>
                  <Text style={styles.contactLabel}>{contact.label}</Text>
                  <Text style={styles.contactMeta}>{formatStatusDetail(status)}</Text>
                </View>
                <View
                  style={[
                    styles.enrollmentPill,
                    isEnrolled ? styles.enrollmentPillReady : styles.enrollmentPillMissing,
                  ]}>
                  <Text style={styles.enrollmentPillText}>
                    {isEnrolled ? 'Enrolled' : 'Missing'}
                  </Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={styles.selectedPanel}>
          <Text style={styles.selectedEyebrow}>Selected Caller</Text>
          <Text style={styles.selectedName}>{selectedContact.callerName}</Text>
          <Text style={styles.selectedStatus}>{formatStatusDetail(selectedStatus)}</Text>
        </View>

        <View style={styles.actions}>
          <TouchableOpacity style={styles.primaryButton} onPress={startSelectedContactCall}>
            <Text style={styles.primaryButtonText}>Simulate Selected Contact</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryButton} onPress={startUnknownCallerCall}>
            <Text style={styles.secondaryButtonText}>Simulate Unknown Caller</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#121212',
  },
  content: {
    padding: 20,
    paddingBottom: 32,
  },
  statusCard: {
    backgroundColor: '#1E1E1E',
    padding: 20,
    borderRadius: 10,
    marginTop: 20,
    borderWidth: 1,
    borderColor: '#333',
  },
  statusTitle: {
    color: '#888',
    fontSize: 14,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  statusActive: {
    color: '#4CAF50',
    fontSize: 20,
    fontWeight: 'bold',
    marginTop: 10,
    textTransform: 'capitalize',
  },
  statusOffline: {
    color: '#FF3B30',
  },
  statusText: {
    color: '#CCC',
    fontSize: 14,
    marginTop: 5,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 28,
    marginBottom: 12,
  },
  sectionTitle: {
    color: '#F5F5F5',
    fontSize: 22,
    fontWeight: '700',
  },
  refreshButton: {
    borderWidth: 1,
    borderColor: '#3A3A3A',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  refreshButtonText: {
    color: '#CFCFCF',
    fontSize: 13,
    fontWeight: '600',
  },
  contactList: {
    gap: 10,
  },
  contactCard: {
    backgroundColor: '#1A1A1A',
    borderColor: '#2F2F2F',
    borderRadius: 10,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
  },
  contactCardSelected: {
    borderColor: '#4CAF50',
    backgroundColor: '#172017',
  },
  contactTextBlock: {
    flex: 1,
    paddingRight: 12,
  },
  contactName: {
    color: '#F2F2F2',
    fontSize: 18,
    fontWeight: '700',
  },
  contactLabel: {
    color: '#9F9F9F',
    fontSize: 13,
    marginTop: 4,
  },
  contactMeta: {
    color: '#C9C9C9',
    fontSize: 12,
    marginTop: 8,
  },
  enrollmentPill: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  enrollmentPillReady: {
    backgroundColor: '#2E7D32',
  },
  enrollmentPillMissing: {
    backgroundColor: '#4A4A4A',
  },
  enrollmentPillText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  selectedPanel: {
    backgroundColor: '#202020',
    borderColor: '#3A3A3A',
    borderRadius: 10,
    borderWidth: 1,
    marginTop: 20,
    padding: 18,
  },
  selectedEyebrow: {
    color: '#888',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  selectedName: {
    color: '#FFFFFF',
    fontSize: 24,
    fontWeight: '800',
    marginTop: 8,
  },
  selectedStatus: {
    color: '#CFCFCF',
    fontSize: 14,
    marginTop: 6,
  },
  actions: {
    marginTop: 24,
    gap: 12,
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: '#4CAF50',
    borderRadius: 10,
    paddingVertical: 15,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '800',
  },
  secondaryButton: {
    alignItems: 'center',
    backgroundColor: '#252525',
    borderColor: '#444',
    borderRadius: 10,
    borderWidth: 1,
    paddingVertical: 15,
  },
  secondaryButtonText: {
    color: '#E8E8E8',
    fontSize: 16,
    fontWeight: '700',
  },
});

export default HomeScreen;
