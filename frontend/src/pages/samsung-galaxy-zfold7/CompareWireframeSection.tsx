import { DeviceWireframeSvg } from "./DeviceWireframeSvg";
import styles from "./CompareWireframeSection.module.css";

const DEFAULT_STEPS = [
  "打开外屏预览，选择海岸星光光效滤镜",
  "在「宠物模式」下抓拍下一张对比自拍",
  "AI 选中最佳瞬间并自动合成宣传卡片",
];

export type CompareWireframeSectionProps = {
  /** 右侧「场景」小窗示意（可选） */
  sceneUrl: string;
  /** 主预览区图片，缺省为渐变占位 */
  mockPhotoSrc?: string;
  /** AI 条带内上下两个小预览（可与 sceneUrl 相同或另图） */
  mockSceneSrc?: string;
  steps?: string[];
};

/**
 * 替换原 shootCompare 里「线框稿 + 双 mock 卡片」区块：
 * 左：设备线稿示意；右：广告风「Z Fold7 × 你的照片」+ 9:16 取景框示意 + 步骤与场景链接。
 */
export function CompareWireframeSection({
  sceneUrl,
  mockPhotoSrc,
  mockSceneSrc = sceneUrl,
  steps = DEFAULT_STEPS,
}: CompareWireframeSectionProps) {
  return (
    <section className={styles.wrap} aria-label="对比示意与线稿">
      <div className={styles.grid}>
        <figure className={styles.sketch}>
          <div className={styles.sketchPlate}>
            <DeviceWireframeSvg className={styles.sketchSvg} />
          </div>
          <figcaption className={styles.sketchCap}>
            设备线稿示意 · 非实物摄影；折痕与镜头模组位置仅供版式参考。
          </figcaption>
        </figure>

        <div className={styles.teaser}>
          <div className={styles.teaserBrand}>
            <span>Galaxy Z Fold7</span>
            <span className={styles.brandX}>×</span>
            <span>你的照片</span>
          </div>
          <p className={styles.tagline}>海岸星光</p>

          <div className={styles.phoneShell}>
            <div className={styles.phoneInner}>
              <div className={styles.shutterRail} aria-hidden>
                <span className={styles.shutterDot} />
              </div>
              <div className={styles.stage}>
                {mockPhotoSrc ? (
                  <img className={styles.stageImg} src={mockPhotoSrc} alt="" />
                ) : (
                  <div className={styles.stageFallback}>上传照片 · 取景示意</div>
                )}
              </div>
              <div className={styles.aiRail} aria-hidden>
                <span className={styles.aiLabel}>AI</span>
                <div className={styles.aiChip}>
                  <img src={mockSceneSrc} alt="" />
                </div>
                <div className={styles.aiChip}>
                  <img src={mockPhotoSrc || mockSceneSrc} alt="" />
                </div>
              </div>
            </div>
          </div>

          <div className={styles.ctaStrip}>
            <span className={styles.ctaGlow} aria-hidden />
            <span>AI 构图建议 · 一键导出对比卡</span>
          </div>

          {steps.length > 0 ? (
            <ol className={styles.steps}>
              {steps.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ol>
          ) : null}

          <p className={styles.sceneLink}>
            场景示意资源：{" "}
            <a href={sceneUrl} target="_blank" rel="noreferrer noopener">
              {sceneUrl}
            </a>
          </p>
        </div>
      </div>
    </section>
  );
}
