type BrandWordmarkProps = {
  className?: string;
  alt?: string;
};

export default function BrandWordmark({ className, alt = "Quorum" }: BrandWordmarkProps) {
  return (
    <>
      <img className={`${className || ""} theme-logo-light`.trim()} src="/brand/quorum-wordmark-dark.svg" alt={alt} />
      <img className={`${className || ""} theme-logo-dark`.trim()} src="/brand/quorum-wordmark-light.svg" alt={alt} />
    </>
  );
}
