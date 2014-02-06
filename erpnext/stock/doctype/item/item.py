# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import webnotes

from webnotes.utils import cstr, flt
from webnotes.model.doc import addchild
from webnotes.model.bean import getlist
from webnotes import msgprint, _

from webnotes.model.controller import DocListController

class WarehouseNotSet(Exception): pass

class DocType(DocListController):
	def onload(self):
		self.doc.fields["__sle_exists"] = self.check_if_sle_exists()
	
	def autoname(self):
		if webnotes.conn.get_default("item_naming_by")=="Naming Series":
			from webnotes.model.doc import make_autoname
			self.doc.item_code = make_autoname(self.doc.naming_series+'.#####')
		elif not self.doc.item_code:
			msgprint(_("Item Code (item_code) is mandatory because Item naming is not sequential."), raise_exception=1)
			
		self.doc.name = self.doc.item_code
			
	def validate(self):
		if not self.doc.stock_uom:
			msgprint(_("Please enter Default Unit of Measure"), raise_exception=1)
		
		self.check_warehouse_is_set_for_stock_item()
		self.check_stock_uom_with_bin()
		self.add_default_uom_in_conversion_factor_table()
		self.validate_conversion_factor()
		self.validate_item_type()
		self.check_for_active_boms()
		self.fill_customer_code()
		self.check_item_tax()
		self.validate_barcode()
		self.cant_change()
		self.validate_item_type_for_reorder()

		if self.doc.name:
			self.old_page_name = webnotes.conn.get_value('Item', self.doc.name, 'page_name')
			
	def on_update(self):
		self.validate_name_with_item_group()
		self.update_item_price()

	def check_warehouse_is_set_for_stock_item(self):
		if self.doc.is_stock_item=="Yes" and not self.doc.default_warehouse:
			webnotes.msgprint(_("Default Warehouse is mandatory for Stock Item."),
				raise_exception=WarehouseNotSet)
			
	def add_default_uom_in_conversion_factor_table(self):
		uom_conv_list = [d.uom for d in self.doclist.get({"parentfield": "uom_conversion_details"})]
		if self.doc.stock_uom not in uom_conv_list:
			ch = addchild(self.doc, 'uom_conversion_details', 'UOM Conversion Detail', self.doclist)
			ch.uom = self.doc.stock_uom
			ch.conversion_factor = 1
			
		for d in self.doclist.get({"parentfield": "uom_conversion_details"}):
			if d.conversion_factor == 1 and d.uom != self.doc.stock_uom:
				self.doclist.remove(d)
				

	def check_stock_uom_with_bin(self):
		if not self.doc.fields.get("__islocal"):
			matched=True
			ref_uom = webnotes.conn.get_value("Stock Ledger Entry", 
				{"item_code": self.doc.name}, "stock_uom")
			if ref_uom:
				if cstr(ref_uom) != cstr(self.doc.stock_uom):
					matched = False
			else:
				bin_list = webnotes.conn.sql("select * from tabBin where item_code=%s", 
					self.doc.item_code, as_dict=1)
				for bin in bin_list:
					if (bin.reserved_qty > 0 or bin.ordered_qty > 0 or bin.indented_qty > 0 \
						or bin.planned_qty > 0) and cstr(bin.stock_uom) != cstr(self.doc.stock_uom):
							matched = False
							break
						
				if matched and bin_list:
					webnotes.conn.sql("""update tabBin set stock_uom=%s where item_code=%s""",
						(self.doc.stock_uom, self.doc.name))
				
			if not matched:
				webnotes.throw(_("Default Unit of Measure can not be changed directly because you have already made some transaction(s) with another UOM. To change default UOM, use 'UOM Replace Utility' tool under Stock module."))
	
	def validate_conversion_factor(self):
		check_list = []
		for d in getlist(self.doclist,'uom_conversion_details'):
			if cstr(d.uom) in check_list:
				msgprint(_("UOM %s has been entered more than once in Conversion Factor Table." %
				 	cstr(d.uom)), raise_exception=1)
			else:
				check_list.append(cstr(d.uom))

			if d.uom and cstr(d.uom) == cstr(self.doc.stock_uom) and flt(d.conversion_factor) != 1:
					msgprint(_("""Conversion Factor of UOM: %s should be equal to 1. As UOM: %s is Stock UOM of Item: %s.""" % 
						(d.uom, d.uom, self.doc.name)), raise_exception=1)
			elif d.uom and cstr(d.uom)!= self.doc.stock_uom and flt(d.conversion_factor) == 1:
				msgprint(_("""Conversion Factor of UOM: %s should not be equal to 1. As UOM: %s is not Stock UOM of Item: %s""" % 
					(d.uom, d.uom, self.doc.name)), raise_exception=1)
					
	def validate_item_type(self):
		if cstr(self.doc.is_manufactured_item) == "No":
			self.doc.is_pro_applicable = "No"

		if self.doc.is_pro_applicable == 'Yes' and self.doc.is_stock_item == 'No':
			webnotes.throw(_("As Production Order can be made for this item, \
				it must be a stock item."))

		if self.doc.has_serial_no == 'Yes' and self.doc.is_stock_item == 'No':
			msgprint("'Has Serial No' can not be 'Yes' for non-stock item", raise_exception=1)
			
	def check_for_active_boms(self):
		if self.doc.is_purchase_item != "Yes":
			bom_mat = webnotes.conn.sql("""select distinct t1.parent 
				from `tabBOM Item` t1, `tabBOM` t2 where t2.name = t1.parent 
				and t1.item_code =%s and ifnull(t1.bom_no, '') = '' and t2.is_active = 1 
				and t2.docstatus = 1 and t1.docstatus =1 """, self.doc.name)
				
			if bom_mat and bom_mat[0][0]:
				webnotes.throw(_("Item must be a purchase item, \
					as it is present in one or many Active BOMs"))
					
		if self.doc.is_manufactured_item != "Yes":
			bom = webnotes.conn.sql("""select name from `tabBOM` where item = %s 
				and is_active = 1""", (self.doc.name,))
			if bom and bom[0][0]:
				webnotes.throw(_("""Allow Bill of Materials should be 'Yes'. Because one or many \
					active BOMs present for this item"""))
					
	def fill_customer_code(self):
		""" Append all the customer codes and insert into "customer_code" field of item table """
		cust_code=[]
		for d in getlist(self.doclist,'item_customer_details'):
			cust_code.append(d.ref_code)
		self.doc.customer_code=','.join(cust_code)

	def check_item_tax(self):
		"""Check whether Tax Rate is not entered twice for same Tax Type"""
		check_list=[]
		for d in getlist(self.doclist,'item_tax'):
			if d.tax_type:
				account_type = webnotes.conn.get_value("Account", d.tax_type, "account_type")
				
				if account_type not in ['Tax', 'Chargeable', 'Income Account', 'Expense Account']:
					msgprint("'%s' is not Tax / Chargeable / Income / Expense Account" % d.tax_type, raise_exception=1)
				else:
					if d.tax_type in check_list:
						msgprint("Rate is entered twice for: '%s'" % d.tax_type, raise_exception=1)
					else:
						check_list.append(d.tax_type)
						
	def validate_barcode(self):
		if self.doc.barcode:
			duplicate = webnotes.conn.sql("""select name from tabItem where barcode = %s 
				and name != %s""", (self.doc.barcode, self.doc.name))
			if duplicate:
				msgprint("Barcode: %s already used in item: %s" % 
					(self.doc.barcode, cstr(duplicate[0][0])), raise_exception = 1)

	def cant_change(self):
		if not self.doc.fields.get("__islocal"):
			vals = webnotes.conn.get_value("Item", self.doc.name, 
				["has_serial_no", "is_stock_item", "valuation_method"], as_dict=True)
			
			if vals and ((self.doc.is_stock_item == "No" and vals.is_stock_item == "Yes") or 
				vals.has_serial_no != self.doc.has_serial_no or 
				cstr(vals.valuation_method) != cstr(self.doc.valuation_method)):
					if self.check_if_sle_exists() == "exists":
						webnotes.throw(_("As there are existing stock transactions for this item, you can not change the values of 'Has Serial No', 'Is Stock Item' and 'Valuation Method'"))
							
	def validate_item_type_for_reorder(self):
		if self.doc.re_order_level or len(self.doclist.get({"parentfield": "item_reorder", 
				"material_request_type": "Purchase"})):
			if not self.doc.is_purchase_item:
				webnotes.msgprint(_("""To set reorder level, item must be Purchase Item"""), 
					raise_exception=1)
	
	def check_if_sle_exists(self):
		sle = webnotes.conn.sql("""select name from `tabStock Ledger Entry` 
			where item_code = %s""", self.doc.name)
		return sle and 'exists' or 'not exists'

	def validate_name_with_item_group(self):
		# causes problem with tree build
		if webnotes.conn.exists("Item Group", self.doc.name):
			webnotes.msgprint("An item group exists with same name (%s), \
				please change the item name or rename the item group" % 
				self.doc.name, raise_exception=1)

	def update_item_price(self):
		webnotes.conn.sql("""update `tabItem Price` set item_name=%s, 
			item_description=%s, modified=NOW() where item_code=%s""",
			(self.doc.item_name, self.doc.description, self.doc.name))

	def get_page_title(self):
		if self.doc.name==self.doc.item_name:
			page_name_from = self.doc.name
		else:
			page_name_from = self.doc.name + " " + self.doc.item_name
		
		return page_name_from
		
	def get_tax_rate(self, tax_type):
		return { "tax_rate": webnotes.conn.get_value("Account", tax_type, "tax_rate") }

	def get_file_details(self, arg = ''):
		file = webnotes.conn.sql("select file_group, description from tabFile where name = %s", eval(arg)['file_name'], as_dict = 1)

		ret = {
			'file_group'	:	file and file[0]['file_group'] or '',
			'description'	:	file and file[0]['description'] or ''
		}
		return ret
		
	def on_trash(self):
		webnotes.conn.sql("""delete from tabBin where item_code=%s""", self.doc.item_code)

	def before_rename(self, olddn, newdn, merge=False):
		if merge:
			# Validate properties before merging
			if not webnotes.conn.exists("Item", newdn):
				webnotes.throw(_("Item ") + newdn +_(" does not exists"))
			
			field_list = ["stock_uom", "is_stock_item", "has_serial_no", "has_batch_no"]
			new_properties = [cstr(d) for d in webnotes.conn.get_value("Item", newdn, field_list)]
			if new_properties != [cstr(self.doc.fields[fld]) for fld in field_list]:
				webnotes.throw(_("To merge, following properties must be same for both items")
					+ ": \n" + ", ".join([self.meta.get_label(fld) for fld in field_list]))

			webnotes.conn.sql("delete from `tabBin` where item_code=%s", olddn)

	def after_rename(self, olddn, newdn, merge):
		webnotes.conn.set_value("Item", newdn, "item_code", newdn)
			
		if merge:
			self.set_last_purchase_rate(newdn)
			self.recalculate_bin_qty(newdn)
			
	def set_last_purchase_rate(self, newdn):
		from erpnext.buying.utils import get_last_purchase_details
		last_purchase_rate = get_last_purchase_details(newdn).get("purchase_rate", 0)
		webnotes.conn.set_value("Item", newdn, "last_purchase_rate", last_purchase_rate)
			
	def recalculate_bin_qty(self, newdn):
		from erpnext.utilities.repost_stock import repost_stock
		webnotes.conn.auto_commit_on_many_writes = 1
		webnotes.conn.set_default("allow_negative_stock", 1)
		
		for warehouse in webnotes.conn.sql("select name from `tabWarehouse`"):
			repost_stock(newdn, warehouse[0])
		
		webnotes.conn.set_default("allow_negative_stock", 
			webnotes.conn.get_value("Stock Settings", None, "allow_negative_stock"))
		webnotes.conn.auto_commit_on_many_writes = 0

def validate_end_of_life(item_code, end_of_life=None, verbose=1):
	if not end_of_life:
		end_of_life = webnotes.conn.get_value("Item", item_code, "end_of_life")
	
	from webnotes.utils import getdate, now_datetime, formatdate
	if end_of_life and getdate(end_of_life) <= now_datetime().date():
		msg = (_("Item") + " %(item_code)s: " + _("reached its end of life on") + \
			" %(date)s. " + _("Please check") + ": %(end_of_life_label)s " + \
			"in Item master") % {
				"item_code": item_code,
				"date": formatdate(end_of_life),
				"end_of_life_label": webnotes.get_doctype("Item").get_label("end_of_life")
			}
		
		_msgprint(msg, verbose)
		
def validate_is_stock_item(item_code, is_stock_item=None, verbose=1):
	if not is_stock_item:
		is_stock_item = webnotes.conn.get_value("Item", item_code, "is_stock_item")
		
	if is_stock_item != "Yes":
		msg = (_("Item") + " %(item_code)s: " + _("is not a Stock Item")) % {
			"item_code": item_code,
		}
		
		_msgprint(msg, verbose)
		
def validate_cancelled_item(item_code, docstatus=None, verbose=1):
	if docstatus is None:
		docstatus = webnotes.conn.get_value("Item", item_code, "docstatus")
	
	if docstatus == 2:
		msg = (_("Item") + " %(item_code)s: " + _("is a cancelled Item")) % {
			"item_code": item_code,
		}
		
		_msgprint(msg, verbose)

def _msgprint(msg, verbose):
	if verbose:
		msgprint(msg, raise_exception=True)
	else:
		raise webnotes.ValidationError, msg