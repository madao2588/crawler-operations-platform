import '../../../../shared/models/page_data.dart';
import '../models/notice_models.dart';

abstract class NoticeRepository {
  Future<List<NoticeSourceSiteOption>> fetchSourceSites();

  Future<PageData<NoticeListItemModel>> fetchNotices({
    int page = 1,
    int pageSize = 20,
    String? keyword,
    String? category,
    String? reviewStatus,
    bool? archived,
    bool? capturedToday,
    String? sourceSite,
    bool? keywordHit,
    bool? highPriority,
    bool? highQuality,
    String? projectSignal,
  });

  Future<NoticeDetailModel> fetchNoticeDetail(int id);

  Future<NoticeSnapshotModel> fetchSnapshot(int id);

  Future<NoticeDetailModel> updateNoticeReview(
    int id,
    NoticeReviewPayload payload,
  );

  /// 导出采集库原始行（UTF-8 BOM CSV），[limit] 最大 10000。
  Future<List<int>> downloadCollectedDataExport({
    int limit = 5000,
    int? taskId,
    String? category,
    String? reviewStatus,
    bool? archived,
  });

  Future<List<int>> downloadInformationPoolExcel({
    int limit = 5000,
    int? taskId,
    String? category,
    String? reviewStatus,
    bool? archived,
  });
}
