import { useMemo, useRef, useState, type ChangeEvent } from 'react'
import { uploadWorkspaceFile, type CartridgeInput } from '../../api.ts'
import { resolveRunInputDefault } from './inputDefaults.ts'

export function RunInputDialog({
  inputs,
  disabled,
  onSubmit,
  onCancel,
}: {
  inputs: CartridgeInput[]
  disabled?: boolean
  onSubmit: (values: Record<string, string>) => void
  onCancel: () => void
}) {
  const filePickerRef = useRef<HTMLInputElement | null>(null)
  const [uploadFieldId, setUploadFieldId] = useState('')
  const [uploadingFile, setUploadingFile] = useState(false)
  const [uploadInfo, setUploadInfo] = useState<{ fieldId: string; filename: string; path: string } | null>(null)
  const [uploadError, setUploadError] = useState('')
  const [values, setValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {}
    inputs.forEach((input) => {
      initial[input.id] = resolveRunInputDefault(input)
    })
    return initial
  })
  const missingRequiredInputs = useMemo(() => {
    return inputs.filter((input) => input.required && !String(values[input.id] || '').trim())
  }, [inputs, values])
  const canStart = !disabled && !uploadingFile && missingRequiredInputs.length === 0
  const pickUploadFile = (id: string) => {
    setUploadFieldId(id)
    setUploadError('')
    filePickerRef.current?.click()
  }
  const handleUploadFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !uploadFieldId) return
    setUploadingFile(true)
    setUploadError('')
    try {
      const result = await uploadWorkspaceFile(file)
      setValues((current) => ({ ...current, [uploadFieldId]: result.path }))
      setUploadInfo({ fieldId: uploadFieldId, filename: result.filename, path: result.path })
    } catch (error: any) {
      setUploadError(error?.message || '上传失败')
    } finally {
      setUploadingFile(false)
    }
  }
  return (
    <div className="cf-input-modal-backdrop" onClick={onCancel}>
      <div className="cf-input-modal" onClick={(event) => event.stopPropagation()}>
        <div className="cf-input-modal-head">
          <strong>运行输入</strong>
          <button type="button" className="cf-input-modal-close" onClick={onCancel}>x</button>
        </div>
        <div className="cf-input-form">
          <p className="cf-input-form-hint">这些字段会作为本次真实运行的输入传入流程。</p>
          <div className="cf-input-fields">
            <input
              ref={filePickerRef}
              type="file"
              style={{ display: 'none' }}
              accept=".txt,.md,.markdown,.json,.csv,.log,.html,.htm,.xml,.yaml,.yml,.gd,.tscn,.tres,.png,.jpg,.jpeg,.webp"
              onChange={handleUploadFile}
            />
            {inputs.map((input) => {
              const isFilePathInput = input.id === 'file_path' || input.type === 'file'
              return (
              <div key={input.id} className="cf-input-field">
                <label htmlFor={`cf-input-${input.id}`}>
                  {input.label || input.id}
                  {input.required && <span className="cf-required-star">*</span>}
                </label>
                {isFilePathInput && (
                  <div className="cf-upload-row">
                    <button
                      type="button"
                      className="cf-btn-outline"
                      disabled={disabled || uploadingFile}
                      onClick={() => pickUploadFile(input.id)}
                    >
                      {uploadingFile && uploadFieldId === input.id ? '上传中...' : '上传本地文件'}
                    </button>
                    <span>
                      {uploadInfo && uploadInfo.fieldId === input.id ? `已上传：${uploadInfo.filename}` : '上传后自动填入工作区路径'}
                    </span>
                  </div>
                )}
                {uploadError && isFilePathInput && <div className="cf-upload-error">{uploadError}</div>}
                {input.required && !String(values[input.id] || '').trim() && (
                  <div className="cf-upload-error">该字段不能为空。</div>
                )}
                {input.type === 'textarea' ? (
                  <textarea
                    id={`cf-input-${input.id}`}
                    value={values[input.id] || ''}
                    placeholder={input.placeholder || ''}
                    rows={4}
                    onChange={(event) => setValues((current) => ({ ...current, [input.id]: event.target.value }))}
                  />
                ) : input.type === 'select' && Array.isArray(input.options) ? (
                  <select
                    id={`cf-input-${input.id}`}
                    value={values[input.id] || ''}
                    onChange={(event) => setValues((current) => ({ ...current, [input.id]: event.target.value }))}
                  >
                    {input.options.map((option) => (
                      <option key={option.value} value={option.value}>{option.label || option.value}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={`cf-input-${input.id}`}
                    type={['date', 'number', 'email', 'url'].includes(input.type) ? input.type : 'text'}
                    value={values[input.id] || ''}
                    placeholder={input.placeholder || ''}
                    onChange={(event) => setValues((current) => ({ ...current, [input.id]: event.target.value }))}
                  />
                )}
              </div>
            )})}
          </div>
          <div className="cf-input-actions">
            <button type="button" className="cf-btn-outline" onClick={onCancel}>取消</button>
            <button type="button" className="cf-btn-accent" disabled={!canStart} onClick={() => canStart && onSubmit(values)}>开始运行</button>
          </div>
        </div>
      </div>
    </div>
  )
}
