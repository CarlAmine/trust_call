import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import HomeScreen from './src/screens/HomeScreen';
import CallScreen from './src/screens/CallScreen'; // We imported the new screen!

const Stack = createNativeStackNavigator();

function App(): React.JSX.Element {
  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName="Home">
        <Stack.Screen 
          name="Home" 
          component={HomeScreen} 
          options={{ 
            title: 'Trust-Call Shield',
            headerStyle: { backgroundColor: '#1E1E1E' },
            headerTintColor: '#fff'
          }} 
        />
        {/* We registered the new screen here! */}
        <Stack.Screen 
          name="Call" 
          component={CallScreen} 
          options={{ headerShown: false }} // Hides the top bar during a call to look native
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

export default App;