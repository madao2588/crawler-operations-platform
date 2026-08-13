export const COLLECTION_COMPLETENESS_HELP =
  '采集完整度：根据标题、正文长度、乱码和结构完整性计算，不代表公告重要性'

export function collectionCompletenessLabel(score: number) {
  return `采集完整度 ${score}`
}
