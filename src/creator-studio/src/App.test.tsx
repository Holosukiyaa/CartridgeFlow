import { fireEvent, render, screen } from '@testing-library/react'
import App from './App'

describe('creator studio authoring flow', () => {
  it('accepts selected AI changes and lets a creator freeze a direct canvas edit', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: '审阅 AI 变更' }))
    expect(screen.getByText('AI 建议了 3 项改动')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /调整：简报使用交叉核对结果/ }))
    fireEvent.click(screen.getByRole('button', { name: '接受 3 项修改' }))
    expect(screen.getAllByText('提取公告关键数字').length).toBeGreaterThan(0)
    fireEvent.click(screen.getAllByRole('button', { name: '固化此步骤' })[0])
    expect(screen.getAllByText('已固化').length).toBeGreaterThan(2)
  })

  it('resolves the plain-language blocker before enabling generation', () => {
    render(<App />)
    const generate = screen.getByRole('button', { name: /生成 cartridge/ })
    expect(generate).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '补充' }))
    expect(screen.getByText('阻塞项已解决，设计可继续验证。')).toBeInTheDocument()
    expect(screen.queryByText('阻塞：需要监管公告网址')).not.toBeInTheDocument()
  })
})
