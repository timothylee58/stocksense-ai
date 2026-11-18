import { Link, Stack } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { colors, space } from "@/lib/theme";

export default function NotFoundScreen() {
  return (
    <>
      <Stack.Screen options={{ title: "Not found" }} />
      <View style={styles.container}>
        <Text style={styles.title}>Screen not found</Text>
        <Link href="/" style={styles.link}>
          Back to Ops console
        </Link>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: "center",
    justifyContent: "center",
    gap: space.sm,
  },
  title: { color: colors.text, fontSize: 18, fontWeight: "700" },
  link: { color: colors.accent, fontSize: 13 },
});
