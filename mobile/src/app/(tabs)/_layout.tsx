import { Ionicons } from "@expo/vector-icons";
import { Tabs } from "expo-router";

import { colors } from "@/lib/theme";

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.text,
        tabBarInactiveTintColor: colors.faint,
        tabBarStyle: {
          backgroundColor: colors.panelAlt,
          borderTopColor: colors.border,
          borderTopWidth: 1,
          elevation: 0,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "600", letterSpacing: 0.6 },
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Ops",
          tabBarIcon: ({ color, size }) => <Ionicons name="pulse" color={String(color)} size={size} />,
        }}
      />
      <Tabs.Screen
        name="predict"
        options={{
          title: "Predict",
          tabBarIcon: ({ color, size }) => <Ionicons name="analytics" color={String(color)} size={size} />,
        }}
      />
      <Tabs.Screen
        name="trade"
        options={{
          title: "Trade",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="swap-horizontal" color={String(color)} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
