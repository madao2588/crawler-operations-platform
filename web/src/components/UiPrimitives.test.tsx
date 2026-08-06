import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataTableShell, DetailDrawer, MetricStrip } from './UiPrimitives'

describe('shared UI primitives', () => {
  it('closes an open detail drawer with Escape', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <DetailDrawer open title="公告详情" onClose={onClose}>
        <p>详情内容</p>
      </DetailDrawer>,
    )

    expect(screen.getByRole('dialog', { name: '公告详情' })).toBeVisible()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('announces the active metric as selected', () => {
    render(
      <MetricStrip
        ariaLabel="规则统计"
        items={[
          { key: 'all', label: '规则总数', value: 8, active: true, onClick: vi.fn() },
          { key: 'active', label: '已启用', value: 5, onClick: vi.fn() },
        ]}
      />,
    )

    expect(screen.getByRole('button', { name: '规则总数 8' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '已启用 5' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('exposes one consistent data-table scroll region', () => {
    render(
      <DataTableShell ariaLabel="规则结果">
        <table><tbody><tr><td>示例</td></tr></tbody></table>
      </DataTableShell>,
    )

    expect(screen.getByRole('region', { name: '规则结果' })).toHaveAttribute('data-scroll-region', 'table')
  })
})
