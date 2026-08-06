enum AppDestination {
  notices,
  sourceSites,
  systemManagement,
}

enum SystemManagementTab {
  tasks,
  logs,
}

class NoticeQuery {
  final String? keyword;
  final String? category;
  final String? reviewStatus;
  final bool? archived;
  final bool? capturedToday;
  final String? sourceSite;
  final bool? keywordHit;
  final bool? highPriority;
  final bool? highQuality;
  final String? projectSignal;

  const NoticeQuery({
    this.keyword,
    this.category,
    this.reviewStatus,
    this.archived,
    this.capturedToday,
    this.sourceSite,
    this.keywordHit,
    this.highPriority,
    this.highQuality,
    this.projectSignal,
  });

  bool get isEmpty =>
      keyword == null &&
      category == null &&
      reviewStatus == null &&
      archived == null &&
      capturedToday == null &&
      sourceSite == null &&
      keywordHit == null &&
      highPriority == null &&
      highQuality == null &&
      projectSignal == null;

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        other is NoticeQuery &&
            keyword == other.keyword &&
            category == other.category &&
            reviewStatus == other.reviewStatus &&
            archived == other.archived &&
            capturedToday == other.capturedToday &&
            sourceSite == other.sourceSite &&
            keywordHit == other.keywordHit &&
            highPriority == other.highPriority &&
            highQuality == other.highQuality &&
            projectSignal == other.projectSignal;
  }

  @override
  int get hashCode => Object.hash(
        keyword,
        category,
        reviewStatus,
        archived,
        capturedToday,
        sourceSite,
        keywordHit,
        highPriority,
        highQuality,
        projectSignal,
      );
}

class AppNavigationIntent {
  final AppDestination destination;
  final NoticeQuery? noticeQuery;
  final int? noticeId;
  final SystemManagementTab? systemTab;
  final String? taskFilter;
  final String? logLevel;
  final int? taskId;

  const AppNavigationIntent.notices({
    NoticeQuery query = const NoticeQuery(),
    this.noticeId,
  })  : destination = AppDestination.notices,
        noticeQuery = query,
        systemTab = null,
        taskFilter = null,
        logLevel = null,
        taskId = null;

  const AppNavigationIntent.sourceSites()
      : destination = AppDestination.sourceSites,
        noticeQuery = null,
        noticeId = null,
        systemTab = null,
        taskFilter = null,
        logLevel = null,
        taskId = null;

  const AppNavigationIntent.systemManagement({
    SystemManagementTab tab = SystemManagementTab.tasks,
    this.taskFilter,
    this.logLevel,
    this.taskId,
  })  : destination = AppDestination.systemManagement,
        noticeQuery = null,
        noticeId = null,
        systemTab = tab;
}
