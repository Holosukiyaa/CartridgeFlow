import {
  ActionIcon,
  Button as MantineButton,
  Checkbox,
  ColorInput,
  Menu as MantineMenu,
  Modal,
  ScrollArea as MantineScrollArea,
  Select,
  Tabs as MantineTabs,
  Textarea,
  TextInput,
  Tooltip as MantineTooltip,
  type ActionIconProps,
  type ButtonProps as MantineButtonProps,
  type ModalProps,
} from '@mantine/core'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonProps = MantineButtonProps & ButtonHTMLAttributes<HTMLButtonElement>

export function Button({ children, type = 'button', ...props }: ButtonProps) {
  return <MantineButton type={type} {...props}>{children}</MantineButton>
}

export function IconButton({ label, children, ...props }: ActionIconProps & { label: string; children: ReactNode }) {
  return <MantineTooltip label={label} openDelay={400}>
    <ActionIcon aria-label={label} {...props}>{children}</ActionIcon>
  </MantineTooltip>
}

export const Field = {
  Text: TextInput,
  Textarea,
  Select,
  Checkbox,
  Color: ColorInput,
}

export const Tabs = MantineTabs
export const Menu = MantineMenu
export const Tooltip = MantineTooltip
export const ScrollArea = MantineScrollArea

export function Dialog({ children, ...props }: ModalProps) {
  return <Modal overlayProps={{ backgroundOpacity: 0.36, blur: 1 }} {...props}>{children}</Modal>
}
