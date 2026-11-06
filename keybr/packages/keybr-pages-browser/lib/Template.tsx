import { isPremiumUser, Pages, usePageData } from "@keybr/pages-shared";
import { AdBanner } from "@keybr/thirdparties";
import { PortalContainer, Toaster } from "@keybr/widget";
import { type ReactNode } from "react";
import { Link } from "react-router";
import { NavMenu } from "./NavMenu.tsx";
import * as styles from "./Template.module.less";

export function Template({
  path,
  children,
}: {
  readonly path: string;
  readonly children: ReactNode;
}) {
  const { publicUser } = usePageData();
  return isPremiumUser(publicUser) ? (
    <div className={styles.bodyAlt}>
      <main className={styles.mainAlt}>
        {children}
        <PortalContainer />
        <Toaster />
      </main>
      <nav className={styles.navAlt}>
        <NavMenu currentPath={path} />
      </nav>
      <EnvName />
    </div>
  ) : (
    <div className={styles.body}>
      <main className={styles.main}>
        {children}
        <PortalContainer />
        <Toaster />
      </main>
      <nav className={styles.nav}>
        <NavMenu currentPath={path} />
      </nav>
      <div className={styles.topbar}>
        {/* The theme gives the light or the dark logo. */}
        <Link
          className={styles.logo}
          to={Pages.practice.path}
          aria-label="typokiller"
        />
      </div>
      <div className={styles.sidebar}>
        <AdBanner name="BANNER_160X600_1" />
      </div>
      <EnvName />
    </div>
  );
}

function EnvName() {
  return process.env.NODE_ENV === "production" ? null : (
    <div
      style={{
        position: "fixed",
        zIndex: "1",
        insetInlineEnd: "0px",
        insetBlockEnd: "0px",
        padding: "5px",
        margin: "5px",
        border: "1px solid red",
        color: "red",
      }}
    >
      {`process.env.NODE_ENV=${process.env.NODE_ENV}`}
    </div>
  );
}
