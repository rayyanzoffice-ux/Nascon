import 'package:flutter/material.dart';
import 'main.dart';
import 'screens.dart';
import 'receipt.dart';
class StoreScreen extends StatefulWidget{
  const StoreScreen({super.key});
  @override State<StoreScreen> createState()=>_StoreScreenState();
}
class _StoreScreenState extends State<StoreScreen>{
  late Future<dynamic> future;
  @override void initState(){super.initState();refresh();}
  void refresh(){future=store.cached('catalogue','/mobile/v1/catalogue');}
  @override Widget build(BuildContext context)=>FutureBuilder<dynamic>(future:future,builder:(context,snapshot){
    final products=snapshot.data is List?snapshot.data as List:[];
    return ListView(padding:const EdgeInsets.all(15),children:[
      header('Club Store','Official kits and accessories'),
      if(snapshot.connectionState==ConnectionState.waiting)const LinearProgressIndicator(),
      if(snapshot.hasError)Text(snapshot.error.toString()),
      ...products.map((product)=>Card(child:Padding(padding:const EdgeInsets.all(16),
        child:Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[
          Container(height:125,decoration:BoxDecoration(color:const Color(0xff183e55),
            borderRadius:BorderRadius.circular(15)),child:const Icon(Icons.checkroom,size:75,color:Color(0xff3dddc9))),
          const SizedBox(height:15),
          Text(product['name'].toString(),style:const TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
          const Text('Premium match-day merchandise',style:TextStyle(color:Colors.white70)),
          const SizedBox(height:12),
          ...((product['variants'] as List?)??[]).map((v)=>Padding(
            padding:const EdgeInsets.symmetric(vertical:5),
            child:Row(children:[
              Expanded(child:Text('Size ${v['size']} • ${v['stock']} in stock')),
              Text('PKR ${(v['price_minor'] as num)/100}'),
              const SizedBox(width:8),
              FilledButton(onPressed:(v['stock'] as int)>0?()=>checkout(context,v):null,child:const Text('Buy')),
            ]),
          )),
        ])))),
      if(products.isEmpty)const ListTile(title:Text('No products currently available')),
    ]);
  });

  Future<void> checkout(BuildContext context,dynamic v) async {
    final confirmed=await showDialog<bool>(context:context,builder:(c)=>AlertDialog(
      title:const Text('Confirm order'),
      content:Text('Purchase one size ${v['size']} jersey?\nPayment: mock gateway'),
      actions:[TextButton(onPressed:()=>Navigator.pop(c,false),child:const Text('Cancel')),
        FilledButton(onPressed:()=>Navigator.pop(c,true),child:const Text('Pay now'))]));
    if(confirmed!=true||!context.mounted)return;
    final id='ord-${DateTime.now().millisecondsSinceEpoch}';
    try{
      final receipt=await store.request('POST','/audit/v1/checkout',data:{
        'order_id':id,'customer_id':store.email.isEmpty?'demo-customer':store.email,
        'items':[{'variant_id':v['variant_id'],'quantity':1}],
        'discount_code':null,'payment':{'token':'tok_success'}
      });
      if(context.mounted){
        Navigator.push(context,MaterialPageRoute(builder:(_)=>ReceiptScreen(data:receipt)));
        setState(refresh);
      }
    }catch(e){if(context.mounted)toast(context,e.toString());}
  }
}
