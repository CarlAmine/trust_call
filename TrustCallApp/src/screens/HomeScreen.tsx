import React, { useEffect, useState } from 'react';
import {
  Alert,
  NativeModules,
  PermissionsAndroid,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { getBackendHttpUrl } from '../config/backend';

type PhoneContact = {
  id: string;
  name: string;
  phoneNumber?: string;
};

type TrustedContact = {
  callerId: string;
  callerName: string;
  label: string;
  phoneNumber?: string;
  phoneDigits?: string;
  source: 'phone' | 'demo';
};

type EnrollmentStatus = {
  caller_id: string;
  enrolled: boolean;
  embedding_dim?: number;
  updated_at_utc?: string | null;
  num_updates?: number;
};

type TrustCallContactsModule = {
  getContacts: () => Promise<PhoneContact[]>;
};

const { TrustCallContacts } = NativeModules as {
  TrustCallContacts?: TrustCallContactsModule;
};

const DEMO_CONTACTS: TrustedContact[] = [
  {
    callerId: 'alice_demo',
    callerName: 'Alice Demo',
    label: '+1 555 0101',
    phoneNumber: '+1 555 0101',
    phoneDigits: '15550101',
    source: 'demo',
  },
  {
    callerId: 'mom_demo',
    callerName: 'Mom Demo',
    label: '+1 555 0102',
    phoneNumber: '+1 555 0102',
    phoneDigits: '15550102',
    source: 'demo',
  },
  {
    callerId: 'bank_contact',
    callerName: 'Bank Contact',
    label: '+1 555 0103',
    phoneNumber: '+1 555 0103',
    phoneDigits: '15550103',
    source: 'demo',
  },
];

const UNKNOWN_INCOMING_CALL = {
  callerId: 'unknown',
  callerName: 'Unknown Caller',
};

const normalizePhoneDigits = (value?: string): string => (value ?? '').replace(/\D/g, '');

const callerIdFromPhoneDigits = (digits: string): string => `contact_${digits || 'unknown'}`;

const normalizeCallerId = (contact: PhoneContact): string => {
  const phoneDigits = normalizePhoneDigits(contact.phoneNumber);
  const stableValue = phoneDigits || contact.id || contact.name;
  const normalized = stableValue.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return `contact_${normalized || 'unknown'}`;
};

const toTrustedContact = (contact: PhoneContact): TrustedContact => {
  const phoneDigits = normalizePhoneDigits(contact.phoneNumber);
  return {
    callerId: phoneDigits ? callerIdFromPhoneDigits(phoneDigits) : normalizeCallerId(contact),
    callerName: contact.name || contact.phoneNumber || 'Unnamed Contact',
    label: contact.phoneNumber || 'Phone contact',
    phoneNumber: contact.phoneNumber,
    phoneDigits,
    source: 'phone',
  };
};

const phoneNumbersMatch = (left?: string, right?: string) => {
  const leftDigits = normalizePhoneDigits(left);
  const rightDigits = normalizePhoneDigits(right);
  if (!leftDigits || !rightDigits) return false;
  if (leftDigits === rightDigits) return true;

  const suffixLength = Math.min(leftDigits.length, rightDigits.length, 10);
  return suffixLength >= 7 && leftDigits.slice(-suffixLength) === rightDigits.slice(-suffixLength);
};

const requestAndroidPermission = async (
  permission: string,
  title: string,
  message: string,
) => {
  if (Platform.OS !== 'android') return true;

  const granted = await PermissionsAndroid.request(permission as any, {
    title,
    message,
    buttonNeutral: 'Ask Me Later',
    buttonNegative: 'Cancel',
    buttonPositive: 'OK',
  });

  return granted === PermissionsAndroid.RESULTS.GRANTED;
};

const requestCallPermissions = async () => {
  try {
    const granted = await requestAndroidPermission(
      PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
      'Trust Call Microphone Permission',
      'Trust Call needs microphone access to analyze live call audio.',
    );

    if (!granted) {
      Alert.alert(
        'Microphone Required',
        'Trust Call needs microphone access before it can verify the caller voice.',
      );
    }
    return granted;
  } catch (err) {
    console.warn('Error requesting microphone permission:', err);
    return false;
  }
};

const requestContactsPermission = async () => {
  try {
    const granted = await requestAndroidPermission(
      PermissionsAndroid.PERMISSIONS.READ_CONTACTS,
      'Trust Call Contacts Permission',
      'Trust Call uses contacts so you can choose whose voice profile to verify.',
    );

    if (!granted) {
      Alert.alert(
        'Contacts Unavailable',
        'Trust Call will show demo contacts until contacts access is allowed.',
      );
    }
    return granted;
  } catch (err) {
    console.warn('Error requesting contacts permission:', err);
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
  const [contacts, setContacts] = useState<TrustedContact[]>(DEMO_CONTACTS);
  const [selectedCallerId, setSelectedCallerId] = useState(DEMO_CONTACTS[0].callerId);
  const [enrollmentByCallerId, setEnrollmentByCallerId] = useState<
    Record<string, EnrollmentStatus | undefined>
  >({});
  const [backendStatus, setBackendStatus] = useState('Checking backend');
  const [contactsStatus, setContactsStatus] = useState('Demo contacts loaded');
  const [searchText, setSearchText] = useState('');
  const [incomingPhoneNumber, setIncomingPhoneNumber] = useState('+1 555 0101');

  const selectedContact =
    contacts.find((contact) => contact.callerId === selectedCallerId) ?? contacts[0];

  const visibleContacts = contacts.filter((contact) => {
    const query = searchText.trim().toLowerCase();
    if (!query) return true;
    return (
      contact.callerName.toLowerCase().includes(query) ||
      contact.label.toLowerCase().includes(query)
    );
  });

  const resolveIncomingContact = (phoneNumber: string): TrustedContact | undefined =>
    contacts.find((contact) => phoneNumbersMatch(contact.phoneNumber ?? contact.label, phoneNumber));

  const refreshEnrollmentStatuses = async (contactsToCheck = contacts) => {
    if (contactsToCheck.length === 0) return;

    setBackendStatus('Checking backend');
    try {
      const entries = await Promise.all(
        contactsToCheck.map(async (contact) => {
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

  const loadPhoneContacts = async () => {
    if (Platform.OS !== 'android' || !TrustCallContacts) {
      setContacts(DEMO_CONTACTS);
      setSelectedCallerId(DEMO_CONTACTS[0].callerId);
      setContactsStatus('Demo contacts loaded');
      await refreshEnrollmentStatuses(DEMO_CONTACTS);
      return;
    }

    const hasContactsPermission = await requestContactsPermission();
    if (!hasContactsPermission) {
      setContacts(DEMO_CONTACTS);
      setSelectedCallerId(DEMO_CONTACTS[0].callerId);
      setContactsStatus('Demo contacts loaded');
      await refreshEnrollmentStatuses(DEMO_CONTACTS);
      return;
    }

    try {
      const phoneContacts = await TrustCallContacts.getContacts();
      const trustedContacts = phoneContacts.map(toTrustedContact).slice(0, 100);

      if (trustedContacts.length === 0) {
        setContacts(DEMO_CONTACTS);
        setSelectedCallerId(DEMO_CONTACTS[0].callerId);
        setContactsStatus('No phone contacts found');
        await refreshEnrollmentStatuses(DEMO_CONTACTS);
        return;
      }

      setContacts(trustedContacts);
      setSelectedCallerId(trustedContacts[0].callerId);
      setContactsStatus(`${trustedContacts.length} phone contacts loaded`);
      await refreshEnrollmentStatuses(trustedContacts);
    } catch (error) {
      console.warn('Failed to load phone contacts:', error);
      setContacts(DEMO_CONTACTS);
      setSelectedCallerId(DEMO_CONTACTS[0].callerId);
      setContactsStatus('Demo contacts loaded');
      await refreshEnrollmentStatuses(DEMO_CONTACTS);
    }
  };

  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', loadPhoneContacts);
    loadPhoneContacts();
    return unsubscribe;
  }, [navigation]);

  const startSelectedContactCall = async () => {
    const hasPermission = await requestCallPermissions();
    if (!hasPermission || !selectedContact) return;

    navigation.navigate('CallScreen', {
      callerId: selectedContact.callerId,
      callerName: selectedContact.callerName,
      phoneNumber: selectedContact.phoneNumber,
      resolvedFromContacts: selectedContact.source === 'phone',
    });
  };

  const startIncomingPhoneCall = async () => {
    const digits = normalizePhoneDigits(incomingPhoneNumber);
    if (!digits) {
      Alert.alert('Incoming Number Required', 'Enter the caller phone number to resolve it.');
      return;
    }

    const hasPermission = await requestCallPermissions();
    if (!hasPermission) return;

    const resolvedContact = resolveIncomingContact(incomingPhoneNumber);
    const caller = resolvedContact ?? {
      callerId: callerIdFromPhoneDigits(digits),
      callerName: `Unknown ${incomingPhoneNumber.trim()}`,
      label: incomingPhoneNumber.trim(),
      phoneNumber: incomingPhoneNumber.trim(),
      phoneDigits: digits,
      source: 'demo' as const,
    };

    navigation.navigate('CallScreen', {
      callerId: caller.callerId,
      callerName: caller.callerName,
      phoneNumber: caller.phoneNumber,
      resolvedFromContacts: Boolean(resolvedContact),
    });
  };

  const startUnknownCallerCall = async () => {
    const hasPermission = await requestCallPermissions();
    if (!hasPermission) return;

    navigation.navigate('CallScreen', UNKNOWN_INCOMING_CALL);
  };

  const selectedStatus = selectedContact
    ? enrollmentByCallerId[selectedContact.callerId]
    : undefined;

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
          <Text style={styles.statusText}>{contactsStatus}</Text>
          <Text style={styles.statusText}>Local speaker profiles: encrypted JSON store</Text>
        </View>

        <View style={styles.incomingPanel}>
          <Text style={styles.selectedEyebrow}>Incoming Call Resolution</Text>
          <Text style={styles.incomingHelp}>
            Enter a caller number. Trust-Call normalizes it, matches phone contacts, and
            uses the resolved contact ID for 1:1 IEP3 verification or TOFU enrollment.
          </Text>
          <TextInput
            style={styles.searchInput}
            placeholder="Incoming phone number"
            placeholderTextColor="#777"
            keyboardType="phone-pad"
            value={incomingPhoneNumber}
            onChangeText={setIncomingPhoneNumber}
          />
          <TouchableOpacity style={styles.primaryButton} onPress={startIncomingPhoneCall}>
            <Text style={styles.primaryButtonText}>Simulate Incoming Number</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Trusted Contacts</Text>
          <TouchableOpacity style={styles.refreshButton} onPress={loadPhoneContacts}>
            <Text style={styles.refreshButtonText}>Refresh</Text>
          </TouchableOpacity>
        </View>

        <TextInput
          style={styles.searchInput}
          placeholder="Search contacts"
          placeholderTextColor="#777"
          value={searchText}
          onChangeText={setSearchText}
        />

        <View style={styles.contactList}>
          {visibleContacts.map((contact) => {
            const status = enrollmentByCallerId[contact.callerId];
            const isSelected = contact.callerId === selectedContact?.callerId;
            const isEnrolled = status?.enrolled === true;

            return (
              <TouchableOpacity
                key={`${contact.callerId}-${contact.label}`}
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

        {selectedContact ? (
          <View style={styles.selectedPanel}>
            <Text style={styles.selectedEyebrow}>Selected Caller</Text>
            <Text style={styles.selectedName}>{selectedContact.callerName}</Text>
            <Text style={styles.selectedStatus}>{formatStatusDetail(selectedStatus)}</Text>
            <Text style={styles.selectedCallerId}>{selectedContact.callerId}</Text>
          </View>
        ) : null}

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
  incomingPanel: {
    backgroundColor: '#181F18',
    borderColor: '#2E7D32',
    borderRadius: 12,
    borderWidth: 1,
    marginTop: 20,
    padding: 18,
    gap: 12,
  },
  incomingHelp: {
    color: '#CFCFCF',
    fontSize: 13,
    lineHeight: 19,
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
  searchInput: {
    backgroundColor: '#1A1A1A',
    borderColor: '#333',
    borderRadius: 10,
    borderWidth: 1,
    color: '#FFFFFF',
    fontSize: 16,
    marginBottom: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
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
  selectedCallerId: {
    color: '#777',
    fontSize: 12,
    marginTop: 8,
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
