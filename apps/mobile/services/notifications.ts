import * as Notifications from "expo-notifications";

export async function scheduleLocalNotification(
  title: string,
  body: string,
  seconds: number = 1
) {
  await Notifications.scheduleNotificationAsync({
    content: {
      title,
      body,
      sound: "default",
      data: { type: "alert" },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
      seconds,
    },
  });
}

export async function scheduleCriticalAlert(title: string, body: string) {
  await scheduleLocalNotification(`[CRITICAL] ${title}`, body, 1);
}
