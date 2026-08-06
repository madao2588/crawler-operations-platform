import { buildNoticeUrl, normalizePath, readNoticeQuery } from './router'

describe('app router', () => {
  it('normalizes unknown routes without breaking valid deep links', () => {
    expect(normalizePath('/notices')).toBe('/notices')
    expect(normalizePath('/does-not-exist')).toBe('/')
  })

  it('round-trips dashboard notice filters through the URL', () => {
    const url = buildNoticeUrl({
      capturedToday: true,
      sourceSite: 'https://www.gov.cn:443',
      keyword: '创新药',
      highPriority: true,
      month: '2026-08',
    })
    const parsed = new URL(url, 'http://localhost')

    expect(parsed.pathname).toBe('/notices')
    expect(readNoticeQuery(parsed.search)).toEqual({
      capturedToday: true,
      sourceSite: 'https://www.gov.cn:443',
      keyword: '创新药',
      highPriority: true,
      month: '2026-08',
    })
  })

  it('ignores malformed month deep links', () => {
    expect(readNoticeQuery('?month=2026-13&keyword=创新药')).toEqual({
      keyword: '创新药',
    })
  })
})
