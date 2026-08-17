import { notifications } from '@mantine/notifications'

const notificationColors = {
  success: 'green',
  error: 'red',
  info: 'blue',
  warning: 'yellow',
  loading: 'blue',
} as const

export function showToast(options: { title: string; description?: string; type?: 'success' | 'error' | 'info' | 'warning' | 'loading' }) {
  const type = options.type || 'info'
  notifications.show({
    title: options.title,
    message: options.description,
    color: notificationColors[type],
    loading: type === 'loading',
    autoClose: type === 'loading' ? false : 3500,
    withBorder: true,
  })
}
