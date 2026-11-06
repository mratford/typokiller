import { type FavIconLink } from "@keybr/assets";
import { allLocales } from "@keybr/intl";
import { type PageInfo, Pages, usePageData } from "@keybr/pages-shared";
import { type ReactNode } from "react";
import { useIntl } from "react-intl";

export function Metas({ page }: { readonly page: PageInfo }): ReactNode {
  const { formatMessage } = useIntl();
  return page.meta.map(({ name, property, content }, index) => {
    if (content != null && typeof content === "object") {
      content = formatMessage(content);
    }
    return (
      <meta key={index} name={name} property={property} content={content} />
    );
  });
}

export function AltLangLinks({ page }: { readonly page: PageInfo }): ReactNode {
  const { base } = usePageData();
  if (
    page.meta.some(
      ({ name, content }) =>
        name === "robots" &&
        typeof content === "string" &&
        content.includes("noindex"),
    )
  ) {
    return null;
  }
  return allLocales
    .map((locale) => ({
      href: String(new URL(Pages.intlPath(page.path, locale), base)),
      rel: "alternate",
      hrefLang: locale,
    }))
    .map((link) => <link key={link.href} {...link} />);
}

// typokiller's icons, from assets/branding/ at the top of the repo.
// The browser also finds root/public/favicon.ico by itself.
export const favIcons: readonly FavIconLink[] = [
  {
    href: "/assets/favicon.svg",
    rel: "icon",
    type: "image/svg+xml",
    sizes: "any",
  },
  {
    href: "/assets/app-icon-192.png",
    rel: "icon",
    type: "image/png",
    sizes: "192x192",
  },
  {
    href: "/assets/app-icon-512.png",
    rel: "icon",
    type: "image/png",
    sizes: "512x512",
  },
  {
    href: "/assets/app-icon-180.png",
    rel: "apple-touch-icon",
    sizes: "180x180",
  },
];
