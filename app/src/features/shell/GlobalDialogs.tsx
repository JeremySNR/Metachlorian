import { AddToDialog } from '../collections/AddToDialog'
import { SendDialog } from '../collections/SendDialog'
import { RightsEditor } from '../rights/RightsEditor'

/** Dialogs any surface can open through the UI store. */
export function GlobalDialogs() {
  return (
    <>
      <AddToDialog />
      <SendDialog />
      <RightsEditor />
    </>
  )
}
