import os, asyncio, discord, json
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import aiohttp

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
LOG_ID = int(os.getenv("LOG_CHANNEL_ID", 0))
ROLE_ID = int(os.getenv("ROLE_CHANNEL_ID", 0))
CVE_CHANNEL_ID = int(os.getenv("CVE_CHANNEL_ID", 0))
NVD_API_KEY = os.getenv("NVD_API_KEY", None)

DISTROS = {
    "Arch": 0x1793D1, "Debian": 0xA80030, "Ubuntu": 0xE95420, "Fedora": 0x294172, "NixOS": 0x5277C3,
    "Gentoo": 0x54487A, "Alpine": 0x0D597F, "Artix": 0x10A0CC, "OpenSUSE": 0x73BA25, "Kali": 0x557C94,
    "Manjaro": 0x35BF5C, "Void": 0x478061, "EndeavourOS": 0x7F7FFF, "Pop!_OS": 0x48B9C7,
    "Elementary": 0x64BAFF, "Linux Mint": 0x87CF3E, "Red Hat": 0xEE0000, "Rocky Linux": 0x10B981,
    "AlmaLinux": 0x2F5BEA, "Slackware": 0x000080, "Zorin OS": 0x15A6F0, "Garuda": 0xFF2E63,
    "Archcraft": 0x2C2C2C, "Solus": 0x5294E2, "MX Linux": 0x333333, "SteamOS": 0x171A21,
    "Parrot OS": 0x00EEFF, "CentOS": 0xFF8B15, "PureOS": 0x202224, "Bedrock": 0x4B4F46
}

class DistroView(discord.ui.View):
    def __init__(self, page=0):
        super().__init__(timeout=None)
        self.page = page
        self.keys = list(DISTROS.keys())
        start = page * 12
        end = start + 12
        for name in self.keys[start:end]:
            self.add_item(DistroButton(name))
        self.add_item(NavButton(-1, page == 0))
        self.add_item(NavButton(1, page >= (len(self.keys) - 1) // 12))

class DistroButton(discord.ui.Button):
    def __init__(self, name):
        super().__init__(label=name, style=discord.ButtonStyle.secondary, custom_id=f"role:{name}")
        self.name = name

    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        role = discord.utils.get(i.guild.roles, name=self.name)
        if role is None:
            role = await i.guild.create_role(name=self.name, color=discord.Color(DISTROS.get(self.name, 0)), reason="Auto role system")
        if role.position >= i.guild.me.top_role.position:
            await i.followup.send("Hierarchy error", ephemeral=True)
            return
        member = i.user
        if role in member.roles:
            await member.remove_roles(role)
            await i.followup.send(f"Removed {self.name}", ephemeral=True)
            return
        await member.add_roles(role)
        await i.followup.send(f"Added {self.name}", ephemeral=True)

class NavButton(discord.ui.Button):
    def __init__(self, delta, disabled):
        label = "PREV" if delta < 0 else "NEXT"
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"nav:{delta}", row=4, disabled=disabled)
        self.delta = delta

    async def callback(self, i: discord.Interaction):
        target = self.view.page + self.delta
        await i.response.edit_message(view=DistroView(target))

class OmniLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log(self, embed):
        channel = self.bot.get_channel(LOG_ID)
        if channel:
            await channel.send(embed=embed)

    def embed(self, title, user=None, color=discord.Color.blurple()):
        e = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
        if user:
            e.set_author(name=str(user), icon_url=user.display_avatar.url)
            e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text="Gen2Bot OmniLog")
        return e

    async def audit_actor(self, guild, action, target_id):
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if entry.target and getattr(entry.target, "id", None) == target_id:
                    return entry.user
        except:
            return None
        return None

    def attach_media(self, embed, message):
        if message.attachments:
            first = message.attachments[0]
            if first.content_type and "image" in first.content_type:
                embed.set_image(url=first.url)
            embed.add_field(name="Attachments", value="\n".join(a.filename for a in message.attachments), inline=False)

    def attach_embeds(self, embed, message):
        if not message.embeds:
            return
        summary = []
        for em in message.embeds[:3]:
            if em.title:
                summary.append(f"**{em.title}**")
            if em.description:
                summary.append(em.description[:200])
            if em.url:
                summary.append(em.url)
            if em.image and em.image.url:
                embed.set_image(url=em.image.url)
            elif em.thumbnail and em.thumbnail.url:
                embed.set_image(url=em.thumbnail.url)
        if summary:
            embed.add_field(name="Embeds", value="\n".join(summary)[:1024], inline=False)

    @commands.Cog.listener()
    async def on_message_delete(self, m):
        if m.author.bot:
            return
        e = self.embed("Message Deleted", m.author, discord.Color.red())
        e.add_field(name="Channel", value=m.channel.mention)
        e.add_field(name="Message ID", value=str(m.id))
        e.add_field(name="Content", value=m.content or "None", inline=False)
        self.attach_media(e, m)
        self.attach_embeds(e, m)
        await self.log(e)

    @commands.Cog.listener()
    async def on_message_edit(self, b, a):
        if b.author.bot or b.content == a.content:
            return
        e = self.embed("Message Edited", a.author, discord.Color.orange())
        e.add_field(name="Channel", value=a.channel.mention)
        e.add_field(name="Message ID", value=str(a.id))
        e.add_field(name="Before", value=b.content or "None", inline=False)
        e.add_field(name="After", value=a.content or "None", inline=False)
        self.attach_embeds(e, a)
        await self.log(e)

    @commands.Cog.listener()
    async def on_member_update(self, b, a):
        added = set(a.roles) - set(b.roles)
        removed = set(b.roles) - set(a.roles)
        if not added and not removed:
            return
        e = self.embed("Role Update", a, discord.Color.blue())
        if added:
            e.add_field(name="Added", value="\n".join(r.name for r in added), inline=False)
        if removed:
            e.add_field(name="Removed", value="\n".join(r.name for r in removed), inline=False)
        actor = await self.audit_actor(a.guild, discord.AuditLogAction.member_role_update, a.id)
        if actor:
            e.add_field(name="By", value=str(actor), inline=False)
        await self.log(e)

    @commands.Cog.listener()
    async def on_member_join(self, m):
        await self.log(self.embed("Member Joined", m, discord.Color.green()))

    @commands.Cog.listener()
    async def on_member_remove(self, m):
        await self.log(self.embed("Member Left", m, discord.Color.dark_gray()))

    @commands.Cog.listener()
    async def on_member_ban(self, g, u):
        actor = await self.audit_actor(g, discord.AuditLogAction.ban, u.id)
        e = self.embed("User Banned", u, discord.Color.dark_red())
        if actor:
            e.add_field(name="By", value=str(actor))
        await self.log(e)

    @commands.Cog.listener()
    async def on_member_unban(self, g, u):
        await self.log(self.embed("User Unbanned", u, discord.Color.green()))

    @commands.Cog.listener()
    async def on_guild_role_create(self, r):
        e = self.embed("Role Created", color=discord.Color.green())
        e.add_field(name="Role", value=r.name)
        await self.log(e)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, r):
        e = self.embed("Role Deleted", color=discord.Color.red())
        e.add_field(name="Role", value=r.name)
        await self.log(e)

    @commands.Cog.listener()
    async def on_guild_role_update(self, b, a):
        changes = []
        if b.name != a.name:
            changes.append(f"Name: {b.name} -> {a.name}")
        if b.color != a.color:
            changes.append("Color changed")
        if b.permissions.value != a.permissions.value:
            changes.append("Permissions changed")
        if b.hoist != a.hoist:
            changes.append(f"Hoist: {b.hoist} -> {a.hoist}")
        if b.mentionable != a.mentionable:
            changes.append(f"Mentionable: {b.mentionable} -> {a.mentionable}")
        if not changes:
            return
        e = self.embed("Role Updated", color=discord.Color.blurple())
        e.add_field(name="Role", value=f"{a.name} ({a.id})")
        e.add_field(name="Changes", value="\n".join(changes)[:1024], inline=False)
        actor = await self.audit_actor(a.guild, discord.AuditLogAction.role_update, a.id)
        if actor:
            e.add_field(name="By", value=str(actor))
        await self.log(e)

    @commands.Cog.listener()
    async def on_voice_state_update(self, m, b, a):
        if b.channel == a.channel:
            return
        e = self.embed("Voice Update", m, discord.Color.purple())
        e.add_field(name="Before", value=str(b.channel) or "None", inline=True)
        e.add_field(name="After", value=str(a.channel) or "None", inline=True)
        await self.log(e)

class CVECog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = NVD_API_KEY
        self.base_url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
        self.session = None
        self.last_cve_check = datetime.now(timezone.utc) - timedelta(days=7)
        self.state_file = "data/posted_cves.json"
        self.bootstrapped = False
        os.makedirs("data", exist_ok=True)
        self._load_state()

    def _load_state(self):
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
                self.last_posted_cves = set(data.get("cves", []))
                if data.get("last_check"):
                    self.last_cve_check = datetime.fromisoformat(data["last_check"])
        except (FileNotFoundError, json.JSONDecodeError):
            self.last_posted_cves = set()

    def _save_state(self):
        data = {
            "cves": list(self.last_posted_cves)[-500:],
            "last_check": self.last_cve_check.isoformat()
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        if not self.cve_checker.is_running():
            self.cve_checker.start()

    async def cog_unload(self):
        if self.session:
            await self.session.close()
        self.cve_checker.cancel()
        self._save_state()

    async def fetch_recent_cves(self):
        now = datetime.now(timezone.utc)
        params = {
            "resultsPerPage": 5,
            "startIndex": 0,
            "pubStartDate": self.last_cve_check.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "pubEndDate": now.strftime("%Y-%m-%dT%H:%M:%S.000"),
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["apiKey"] = self.api_key
        try:
            async with self.session.get(self.base_url, params=params, headers=headers) as resp:
                if resp.status == 404:
                    self.last_cve_check = now
                    self.bootstrapped = True
                    return []
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("vulnerabilities", [])
        except Exception:
            return []

    def should_post_cve(self, cve):
        cve_data = cve.get("cve", {})
        noise_keywords = [
            "codeastro", "sourcecodester", "tenda", "campcodes",
            "oretnom23", "kevinsmith", "phpgurukul", "mayurik",
            "netartmedia", "hospital management system", "student management system",
            "employee management system", "leave management system", "payroll management system",
            "online shopping", "online food", "real estate", "car rental",
            "billing system", "inventory management", "php_", "php-"
        ]
        description_text = ""
        for desc in cve_data.get("descriptions", []):
            if desc.get("lang") == "en":
                description_text = desc.get("value", "").lower()
                break
        metrics = cve_data.get("metrics", {})
        cvss_v3 = metrics.get("cvssMetricV31", [{}])[0].get("cvssData", {})
        severity = cvss_v3.get("baseSeverity", "").upper()
        if severity == "CRITICAL":
            return True
        if severity in ["HIGH", "MEDIUM"]:
            if any(keyword in description_text for keyword in noise_keywords):
                return False
            linux_keywords = [
                "linux", "kernel", "ubuntu", "debian", "red hat",
                "centos", "fedora", "arch", "gentoo", "alpine",
                "oracle linux", "amazon linux", "opensuse", "kali",
                "artix", "manjaro", "void", "nixos"
            ]
            if any(keyword in description_text for keyword in linux_keywords):
                return True
            for ref in cve_data.get("references", []):
                url = ref.get("url", "").lower()
                if any(keyword in url for keyword in ["linux", "kernel.org", "lwn.net"]):
                    return True
            legit_keywords = [
                "docker", "kubernetes", "nginx", "apache", "postgresql",
                "mysql", "mariadb", "redis", "mongodb", "elasticsearch",
                "gitlab", "github enterprise", "jenkins", "wordpress",
                "drupal", "joomla", "nextcloud", "git", "openssh",
                "openssl", "systemd", "wayland", "xorg", "gnome",
                "kde", "qt", "gtk", "glibc", "gcc"
            ]
            if any(keyword in description_text for keyword in legit_keywords):
                return True
        return False

    def create_cve_embed(self, cve):
        cve_data = cve.get("cve", {})
        cve_id = cve_data.get("id", "Unknown")
        description = "No description available"
        for desc in cve_data.get("descriptions", []):
            if desc.get("lang") == "en":
                description = desc.get("value", description)
                if len(description) > 300:
                    description = description[:297] + "..."
                break
        metrics = cve_data.get("metrics", {})
        cvss_v3 = metrics.get("cvssMetricV31", [{}])[0].get("cvssData", {})
        cvss_v2 = metrics.get("cvssMetricV2", [{}])[0].get("cvssData", {})
        cvss_score = cvss_v3.get("baseScore", cvss_v2.get("baseScore", "N/A"))
        severity = cvss_v3.get("baseSeverity", cvss_v2.get("severity", "Unknown"))
        color = discord.Color.blurple()
        if severity == "CRITICAL":
            color = discord.Color.red()
        elif severity == "HIGH":
            color = discord.Color.orange()
        elif severity == "MEDIUM":
            color = discord.Color.yellow()
        elif severity == "LOW":
            color = discord.Color.green()
        title_prefix = "[CRITICAL] " if severity == "CRITICAL" else ""
        embed = discord.Embed(
            title=f"{title_prefix}{cve_id}",
            description=description,
            color=color,
            url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="CVSS Score", value=str(cvss_score), inline=True)
        embed.add_field(name="Severity", value=severity, inline=True)
        published = cve_data.get("published", "")
        if published:
            try:
                pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                embed.add_field(name="Published", value=f"<t:{int(pub_date.timestamp())}:R>", inline=True)
            except:
                pass
        if severity == "CRITICAL" and cvss_v3.get("vectorString"):
            embed.add_field(name="Vector", value=cvss_v3.get("vectorString", "N/A")[:100], inline=False)
        embed.set_footer(text="NVD - National Vulnerability Database")
        return embed

    @commands.hybrid_command(name="fetch_cves")
    @commands.has_permissions(administrator=True)
    async def force_fetch_cves(self, ctx: commands.Context):
        await ctx.defer()
        channel = self.bot.get_channel(CVE_CHANNEL_ID)
        if not channel:
            await ctx.send(f"Channel with ID {CVE_CHANNEL_ID} not found")
            return
        await ctx.send("Fetching latest CVEs...")
        cves = await self.fetch_recent_cves()
        if not cves:
            await ctx.send("No new CVEs found")
            return
        posted = self.last_posted_cves
        count = 0
        for cve in reversed(cves):
            cve_id = cve.get("cve", {}).get("id")
            if cve_id and cve_id not in posted:
                if self.should_post_cve(cve):
                    embed = self.create_cve_embed(cve)
                    await channel.send(embed=embed)
                    self.last_posted_cves.add(cve_id)
                    count += 1
                    await asyncio.sleep(2)
        self.last_cve_check = datetime.now(timezone.utc)
        self._save_state()
        await ctx.send(f"Posted {count} new CVE(s)")

    @commands.hybrid_command(name="test_api")
    @commands.has_permissions(administrator=True)
    async def test_api(self, ctx: commands.Context):
        await ctx.defer()
        headers = {"User-Agent": "DiscordBot/1.0", "Accept": "application/json"}
        if self.api_key:
            headers["apiKey"] = self.api_key
        results = []
        results.append(f"API Key: {'Present' if self.api_key else 'Missing'}")
        test_url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000")
        end = now.strftime("%Y-%m-%dT%H:%M:%S.000")
        params = {"pubStartDate": start, "pubEndDate": end, "resultsPerPage": 1}
        try:
            async with self.session.get(test_url, params=params, headers=headers) as resp:
                results.append(f"Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    results.append(f"Success. Total CVEs: {data.get('totalResults', 'N/A')}")
                else:
                    text = await resp.text()
                    results.append(f"Error: {text[:100]}")
        except Exception as e:
            results.append(f"Exception: {str(e)[:100]}")
        await ctx.send("\n".join(results))

    @tasks.loop(minutes=15)
    async def cve_checker(self):
        await self.bot.wait_until_ready()
        if CVE_CHANNEL_ID == 0:
            return
        channel = self.bot.get_channel(CVE_CHANNEL_ID)
        if not channel:
            return
        cves = await self.fetch_recent_cves()
        if not cves:
            return
        posted = self.last_posted_cves
        for cve in reversed(cves):
            cve_id = cve.get("cve", {}).get("id")
            if cve_id and cve_id not in posted:
                if self.should_post_cve(cve):
                    embed = self.create_cve_embed(cve)
                    await channel.send(embed=embed)
                    self.last_posted_cves.add(cve_id)
                    await asyncio.sleep(3)
        self.last_cve_check = datetime.now(timezone.utc)
        self._save_state()
        if len(self.last_posted_cves) > 500:
            self.last_posted_cves = set(list(self.last_posted_cves)[-500:])

    @cve_checker.before_loop
    async def before_cve_checker(self):
        await self.bot.wait_until_ready()

class Gen2Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())

    async def setup_hook(self):
        await self.add_cog(OmniLogger(self))
        await self.add_cog(CVECog(self))
        self.add_view(DistroView())
        await self.tree.sync()

    async def on_ready(self):
        print(f"online: {self.user}")

bot = Gen2Bot()

@bot.tree.command(name="linux_roles")
@discord.app_commands.checks.has_permissions(administrator=True)
async def linux_roles(i: discord.Interaction):
    await i.response.send_message("Select your distro role!", view=DistroView(0))

bot.run(TOKEN)