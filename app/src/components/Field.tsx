import type { ReactNode } from 'react'
import { Check, ChevronDown, Minus, Plus } from 'lucide-react'
import {
  Button as RacButton, Checkbox as RacCheckbox, ComboBox as RacComboBox, FieldError, Group, Input, Label, ListBox, ListBoxItem,
  NumberField as RacNumberField, Popover, Radio as RacRadio, RadioGroup as RacRadioGroup, Select as RacSelect, SelectValue,
  Switch as RacSwitch, Text, TextArea as RacTextArea, TextField as RacTextField,
  type CheckboxProps, type ComboBoxProps, type NumberFieldProps, type RadioGroupProps, type SelectProps, type SwitchProps, type TextFieldProps,
} from 'react-aria-components'
import { Ic } from './Icon'
import s from './Field.module.css'
import o from './Overlay.module.css'

interface Common {
  label?: ReactNode
  description?: ReactNode
  slateLabel?: boolean
  className?: string
}

const lab = (label: ReactNode, slate?: boolean) => (label ? <Label className={slate ? s.slateLabel : s.label}>{label}</Label> : null)

export function TextField({ label, description, slateLabel, className, placeholder, mono, multiline, ...props }: Common & Omit<TextFieldProps, 'className'> & { placeholder?: string; mono?: boolean; multiline?: boolean }) {
  return (
    <RacTextField {...props} className={[s.field, className].filter(Boolean).join(' ')}>
      {lab(label, slateLabel)}
      {multiline ? <RacTextArea className={[s.textarea, mono && s.mono].filter(Boolean).join(' ')} placeholder={placeholder} /> : <Input className={[s.input, mono && s.mono].filter(Boolean).join(' ')} placeholder={placeholder} />}
      {description && <Text slot="description" className={s.description}>{description}</Text>}
      <FieldError className={s.error} />
    </RacTextField>
  )
}

export function NumberField({ label, description, slateLabel, className, ...props }: Common & Omit<NumberFieldProps, 'className'>) {
  return (
    <RacNumberField {...props} className={[s.field, className].filter(Boolean).join(' ')}>
      {lab(label, slateLabel)}
      <Group className={s.group}>
        <Input className={s.input} />
        <RacButton slot="decrement" className={s.stepper}>
          <Ic icon={Minus} size={14} />
        </RacButton>
        <RacButton slot="increment" className={s.stepper}>
          <Ic icon={Plus} size={14} />
        </RacButton>
      </Group>
      {description && <Text slot="description" className={s.description}>{description}</Text>}
    </RacNumberField>
  )
}

export function Checkbox({ children, className, selection, ...props }: Omit<CheckboxProps, 'className' | 'children'> & { children?: ReactNode; className?: string; selection?: boolean }) {
  return (
    <RacCheckbox {...props} className={[s.checkbox, selection && s.key, className].filter(Boolean).join(' ')}>
      {({ isSelected }) => (
        <>
          <span className={s.box}>{isSelected && <Ic icon={Check} size={12} />}</span>
          {children}
        </>
      )}
    </RacCheckbox>
  )
}

export function Switch({ children, className, ...props }: Omit<SwitchProps, 'className' | 'children'> & { children: ReactNode; className?: string }) {
  return (
    <RacSwitch {...props} className={[s.switch, className].filter(Boolean).join(' ')}>
      <span className={s.track} />
      {children}
    </RacSwitch>
  )
}

export function RadioGroup({ label, children, className, slateLabel, ...props }: Common & Omit<RadioGroupProps, 'className' | 'children'> & { children: ReactNode }) {
  return (
    <RacRadioGroup {...props} className={[s.field, className].filter(Boolean).join(' ')}>
      {lab(label, slateLabel)}
      <div className={s.radioGroup}>{children}</div>
    </RacRadioGroup>
  )
}

export function Radio({ value, children, description }: { value: string; children: ReactNode; description?: ReactNode }) {
  return (
    <RacRadio value={value} className={s.radio}>
      <span className={s.dot} />
      <span className={s.radioText}>
        <span>{children}</span>
        {description && <span className={s.description}>{description}</span>}
      </span>
    </RacRadio>
  )
}

export interface Option {
  id: string
  label: string
  meta?: string
}

export function Select({ label, description, slateLabel, className, options, placeholder, ...props }: Common & Omit<SelectProps<Option>, 'className' | 'children'> & { options: Option[]; placeholder?: string }) {
  return (
    <RacSelect {...props} placeholder={placeholder} className={[s.field, className].filter(Boolean).join(' ')}>
      {lab(label, slateLabel)}
      <RacButton className={s.selectButton}>
        <SelectValue className={s.selectValue} />
        <Ic icon={ChevronDown} size={14} />
      </RacButton>
      {description && <Text slot="description" className={s.description}>{description}</Text>}
      <FieldError className={s.error} />
      <Popover className={o.popover} offset={4}>
        <ListBox items={options} className={s.listbox}>
          {(item) => (
            <ListBoxItem id={item.id} textValue={item.label} className={s.option}>
              {({ isSelected }) => (
                <>
                  <span>{item.label}</span>
                  {item.meta && <span className={s.optionMeta}>{item.meta}</span>}
                  {isSelected && <Ic icon={Check} className={s.optionCheck} />}
                </>
              )}
            </ListBoxItem>
          )}
        </ListBox>
      </Popover>
    </RacSelect>
  )
}

export function ComboBox({ label, description, slateLabel, className, options, placeholder, ...props }: Common & Omit<ComboBoxProps<Option>, 'className' | 'children'> & { options: Option[]; placeholder?: string }) {
  return (
    <RacComboBox {...props} defaultItems={options} className={[s.field, className].filter(Boolean).join(' ')} menuTrigger="focus">
      {lab(label, slateLabel)}
      <div className={s.comboWrap}>
        <Input className={s.comboInput} placeholder={placeholder} />
        <RacButton className={s.comboButton} aria-label="Show options">
          <Ic icon={ChevronDown} size={14} />
        </RacButton>
      </div>
      {description && <Text slot="description" className={s.description}>{description}</Text>}
      <FieldError className={s.error} />
      <Popover className={o.popover} offset={4}>
        <ListBox className={s.listbox}>
          {(item: Option) => (
            <ListBoxItem id={item.id} textValue={item.label} className={s.option}>
              <span>{item.label}</span>
              {item.meta && <span className={s.optionMeta}>{item.meta}</span>}
            </ListBoxItem>
          )}
        </ListBox>
      </Popover>
    </RacComboBox>
  )
}
