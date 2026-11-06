import { test } from "node:test";
import { FakeIntlProvider, PreferredLocaleContext } from "@keybr/intl";
import { PageDataContext } from "@keybr/pages-shared";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { equal, isNotNull, isNull } from "rich-assert";
import { SubMenu } from "./SubMenu.tsx";

test("render", () => {
  const r = render(
    <PageDataContext.Provider
      value={{
        base: "https://www.keybr.com/",
        locale: "en",
        user: null,
        publicUser: {
          id: "userId",
          name: "userName",
          imageUrl: "imageUrl",
          premium: false,
        },
        settings: null,
      }}
    >
      <PreferredLocaleContext.Provider value="pl">
        <FakeIntlProvider>
          <MemoryRouter>
            <SubMenu currentPath="/page" />
          </MemoryRouter>
        </FakeIntlProvider>
      </PreferredLocaleContext.Provider>
    </PageDataContext.Provider>,
  );

  isNotNull(r.queryByText("Polski"));
  isNotNull(r.queryByText("English"));
  equal(
    r
      .getByText(
        "This is a changed copy of keybr.com. Its source is on GitHub.",
      )
      .getAttribute("href"),
    "https://github.com/mratford/typokiller",
  );
  isNull(r.queryByText("Terms of Service"));
  isNull(r.queryByText("Privacy Policy"));

  r.unmount();
});
