import os, asyncio, discord
from discord.ext import commands
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
LOG_ID = int(os.getenv("LOG_CHANNEL_ID", 0))
ROLE_ID = int(os.getenv("ROLE_CHANNEL_ID", 0))
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
        super().__init__(
            label=name,
            style=discord.ButtonStyle.secondary,
            custom_id=f"role:{name}"
        )
        self.name = name

    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)

        role = discord.utils.get(i.guild.roles, name=self.name)
        if role is None:
            role = await i.guild.create_role(
                name=self.name,
                color=discord.Color(DISTROS.get(self.name, 0)),
                reason="Auto role system"
            )

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
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"nav:{delta}",
            row=4,
            disabled=disabled
        )
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
        e = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
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

            embed.add_field(
                name="Attachments",
                value="\n".join(a.filename for a in message.attachments),
                inline=False
            )

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
            embed.add_field(
                name="Embeds",
                value="\n".join(summary)[:1024],
                inline=False
            )

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
            changes.append(f"Name: {b.name} → {a.name}")
        if b.color != a.color:
            changes.append("Color changed")
        if b.permissions.value != a.permissions.value:
            changes.append("Permissions changed")
        if b.hoist != a.hoist:
            changes.append(f"Hoist: {b.hoist} → {a.hoist}")
        if b.mentionable != a.mentionable:
            changes.append(f"Mentionable: {b.mentionable} → {a.mentionable}")

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

class Gen2Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())

    async def setup_hook(self):
        await self.add_cog(OmniLogger(self))
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